import paho.mqtt.client as mqtt
import urllib.request as request
import logging
import logging.config
import json
import os
import shutil
import datetime
import urllib
from queue import Queue
from threading import Thread
from subprocess import call

IMAGE_URL = "http://192.168.37.21/oneshotimage.jpg"
MQTT_HOST = "localhost"
MQTT_PORT = 1883
EVENT_DIR = "/cctv/events"
GRAB_FOR_SECS = 30
FPS = 1
VIDEO_CONVERT = ["avconv", "-r", "1", "-i", "%4d.jpg", "event.mp4"]

MAKER_URL = None
#MAKER_URL = "https://maker.ifttt.com/trigger/gate/with/key/bjS1EJTq2pcD3cCXnhZgi_"


# Load logging config from logging.json
def setup_logging(default_path='logging.json', default_level=logging.INFO, env_key='LOG_CFG'):
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = json.load(f)
            logging.config.dictConfig(config)
            logging.info("Configured logging from json")
    else:
        logging.basicConfig(level=default_level)
        logging.info("Configured logging basic")

def docker_mqtt():
    # Settings for MQTT Server
    DOCKER_MQTT_ADDR = os.environ.get('MOSQUITTO_PORT_1883_TCP_ADDR', None)
    DOCKER_MQTT_PORT = os.environ.get('MOSQUITTO_PORT_1883_TCP_PORT', None)

    if DOCKER_MQTT_PORT is not None and DOCKER_MQTT_ADDR is not None:
        logging.info("Using linked Docker mqtt: " + DOCKER_MQTT_ADDR + ":" + str(DOCKER_MQTT_PORT))
        # We are running in a Linked Docker environment
        # Use Docker Linked Container environment variables for setup
        global MQTT_HOST
        global MQTT_PORT
        MQTT_HOST = DOCKER_MQTT_ADDR
        MQTT_PORT = int(DOCKER_MQTT_PORT)
    else:
        logging.info("Using defaul mqtt server")

def on_connect(client, userdata, rc):
    logging.info("Connected to mqtt")
    # Subscribe to any mqtt channels here
    client.subscribe("GateGuard/Event")


def on_message(client, userdata, msg):
    cctvlogger = logging.getLogger('cctv')
    cctvlogger.debug('MQTT message received: ' + str(msg.payload))
    # Parse the message as json
    json_msg = json.loads(msg.payload.decode("utf-8"))
    userdata.put(json_msg)


def mqtt_listner(out_q):
    cctvlogger = logging.getLogger('cctv')
    cctvlogger.info("MQTT listener started")
    client = mqtt.Client(userdata = out_q)
    client.on_connect = on_connect
    client.on_message = on_message
    cctvlogger.info("Connecting to mqtt server using: " + MQTT_HOST + ":" + str(MQTT_PORT))
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_forever()
    cctvlogger.error("mqtt_listener stopped")


def frame_grabber(in_q, out_q, frameURL):
    cctvlogger = logging.getLogger('cctv')
    cctvlogger.info("Frame Grabber started: " + frameURL)
    event_dir = None
    event_seq = 0
    grabbing = False
    next_grab = datetime.datetime.now()
    end_grab = next_grab
    frame_interval = datetime.timedelta(seconds=1/FPS)
    latest = EVENT_DIR + "/latest"
    while True:
        if not grabbing:
            # Block waiting for an incoming message
            cctvlogger.info("Blocking waiting for a message")
            msg = in_q.get()
            # We got a message so start a new event
            now = datetime.datetime.now()
            cctvlogger.info("Frame Grabber, got Message: " + str(msg))
            end_grab = now + datetime.timedelta(seconds=GRAB_FOR_SECS)
            cctvlogger.info("End of event: " + str(end_grab))
            grabbing = True
            next_grab = now
            dt = msg["logtime"].split('T')
            d = dt[0].split('-').append(dt[1])
            event_dir = EVENT_DIR + '/' + '/'.join(d)
            os.makedirs(event_dir, exist_ok=True)
        else:
            now = datetime.datetime.now()
            # Check to see whether we have another message during the event
            if not in_q.empty():
                # We are already handling an event so extend the event time
                msg = in_q.get()
                cctvlogger.debug("Frame Grabber, got Message: " + str(msg))
                end_grab = now + datetime.timedelta(seconds=GRAB_FOR_SECS)
                cctvlogger.info("End of event extended: " + str(end_grab))

        # Should we grab the next frame?
        if grabbing and now > next_grab:
            # we need to get a frame
            base_filename = event_dir + "/" + str(event_seq).zfill(4)
            request.urlretrieve(IMAGE_URL, base_filename + ".jpg")
            next_grab = next_grab + frame_interval
            event_seq += 1

        # Check to see whether we should end the event
        if grabbing is True and now > end_grab:
            cctvlogger.info("End of event capture...")
            # Finished grabbing the event
            # Link to the latest event from the top level
            os.remove(latest)
            os.symlink(event_dir, latest)
            # Signal to make video thread to do its stuff
            out_q.put(event_dir)
            # Reset
            grabbing = False
            event_seq = 0
            event_dir = None


def make_video(in_q):
    cctvlogger = logging.getLogger('cctv')
    cctvlogger.info("Video processor started")
    while True:
        # Block waiting for an incoming message
        msg = in_q.get()
        cctvlogger.info("Got path: " + str(msg))

        # Convert video
        result = call(VIDEO_CONVERT, cwd=msg)
        if result == 0:
            # The conversion was successful so move the video and remove the jpgs
            pp = str(msg).split('/')
            newpath = '/'.join(pp[:-1])
            vidfile = newpath + '/' + pp[-1].split('.')[0] + ".mp4"
            vidurl = "https://geo-fun.org/events/" + pp[-2] + "/" + pp[-1].split('.')[0] + ".mp4"
            cctvlogger.info("Moving video event file to " + vidfile)
            os.rename(msg + "/event.mp4", vidfile)
            shutil.rmtree(msg, ignore_errors=True)

            #files = glob.glob(msg + "/*.jpg")
            #print("Removing: " + str(files))
            #for file in files:
            #    os.remove(file)

            # Notify event to IFTTT Maker channel
            if MAKER_URL is not None:
                cctvlogger.debug("URL: " + vidurl)
                json_event = urllib.parse.urlencode({"value1": vidurl })
                cctvlogger.debug("Encoded json: " + json_event)
                json_event = json_event.encode('ascii')
                with urllib.request.urlopen(MAKER_URL, json_event) as f:
                    cctvlogger.debug(f.read().decode('utf-8'))


if __name__ == "__main__":
    setup_logging()
    docker_mqtt()
    q1 = Queue()
    q2 = Queue()
    t1 = Thread(target=frame_grabber, args=(q1,q2, IMAGE_URL,))
    t2 = Thread(target=mqtt_listner, args=(q1,))
    t3 = Thread(target=make_video, args=(q2,))
    t1.start()
    t2.start()
    t3.start()
