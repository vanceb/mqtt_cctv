import paho.mqtt.client as mqtt
import urllib.request as request
import logging
import logging.config
import json
import os
import shutil
import datetime
import time
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


def on_connect(client, userdata, rc):
    logging.info("Connected to mqtt")
    # Subscribe to any mqtt channels here
    client.subscribe("GateGuard/Event")


def on_message(client, userdata, msg):
    cctvlogger = logging.getlogger('cctv')
    cctvlogger.debug('MQTT message received: ' + str(msg.payload))
    # Parse the message as json
    json_msg = json.loads(msg.payload.decode("utf-8"))
    userdata.put(json_msg)


def mqtt_listner(out_q):
    client = mqtt.Client(userdata = out_q)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_forever()


def frame_grabber(in_q, out_q, frameURL):
    cctvlogger = logging.getlogger('cctv')
    cctvlogger.info("Frame Grabber started: " + frameURL)
    event_dir = None
    event_seq = 0
    grabbing = False
    next_grab = datetime.datetime.now()
    end_grab = next_grab
    frame_interval = datetime.timedelta(seconds=1/FPS)
    while True:
        if not grabbing:
            # Block waiting for an incoming message
            cctvlogger.info("Blocking waiting for a message")
            msg = in_q.get()
            # We got a message so start a new event
            now = datetime.datetime.now()
            cctvlogger.info("Frame Grabber, got Message: " + str(msg))
            last_event_time = datetime.datetime.fromtimestamp(time.mktime(time.strptime(msg["logtime"], "%Y-%m-%dT%H:%M:%S.%f")))
            end_grab = last_event_time + datetime.timedelta(seconds=GRAB_FOR_SECS)
            cctvlogger.info("End of event: " + str(end_grab))
            grabbing = True
            next_grab = now
            dt = msg["logtime"].split('T')
            event_dir =  EVENT_DIR + '/' + '/'.join(dt)
            os.makedirs(event_dir, exist_ok=True)
        else:
            now = datetime.datetime.now()
            # Check to see whether we have another message during the event
            if not in_q.empty():
                # We are already handling an event so extend the event time
                msg = in_q.get()
                cctvlogger.debug("Frame Grabber, got Message: " + str(msg))
                last_event_time = datetime.datetime.fromtimestamp(time.mktime(time.strptime(msg["logtime"], "%Y-%m-%dT%H:%M:%S.%f")))
                end_grab = last_event_time + datetime.timedelta(seconds=GRAB_FOR_SECS)
                cctvlogger.info("End of event extended: " + str(end_grab))

        # Should we grab the next frame?
        if grabbing and now > next_grab:
            # we need to get a frame
            base_filename = event_dir + "/" + str(event_seq).zfill(4)
            request.urlretrieve(IMAGE_URL, base_filename + ".jpg")
            next_grab = next_grab + frame_interval
            event_seq += 1

        # Check to see whether we should end the event
        if grabbing == True and now > end_grab:
            cctvlogger.info("End of event capture")
            # Finished grabbing the event
            # Signal to make video thread to do its stuff
            out_q.put(event_dir)
            # Reset
            grabbing = False
            event_seq = 0
            event_dir = None


def make_video(in_q):
    cctvlogger = logging.getlogger('cctv')
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
            shutil.rmtree(msg)

            #files = glob.glob(msg + "/*.jpg")
            #print("Removing: " + str(files))
            #for file in files:
            #    os.remove(file)

            # Notify event to IFTTT Maker channel
            maker_url = "https://maker.ifttt.com/trigger/gate/with/key/bjS1EJTq2pcD3cCXnhZgi_"
            cctvlogger.debug("URL: " + vidurl)
            json_event = urllib.parse.urlencode({"value1": vidurl })
            cctvlogger.debug("Encoded json: " + json_event)
            json_event = json_event.encode('ascii')
            with urllib.request.urlopen(maker_url, json_event) as f:
                print(f.read().decode('utf-8'))


if __name__ == "__main__":
    setup_logging()
    q1 = Queue()
    q2 = Queue()
    t1 = Thread(target=frame_grabber, args=(q1,q2, IMAGE_URL,))
    t2 = Thread(target=mqtt_listner, args=(q1,))
    t3 = Thread(target=make_video, args=(q2,))
    t1.start()
    t2.start()
    t3.start()

