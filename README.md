mqtt_cctv
=========

Project to consume mqtt events and capture cctv video based on the events

Run
===

Build
=====

sudo docker build -t vanceb/mqtt_cctv .

Run
===

sudo docker run -d \
         --restart=always \
         --name mqtt_cctv \
         --volume /cctv/events:/cctv/events \
         --link mosquitto:mosquitto \
         vanceb/mqtt_cctv

 Needs
 =====

 https://hub.docker.com/r/ansi/mosquitto/
 https://github.com/vanceb/mqtt_gateway
