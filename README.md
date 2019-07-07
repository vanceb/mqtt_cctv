# Project Archived
This code has been integrated into a broader home automation project on gitlab [https://gitlab.com/vanceb/home_automation](https://gitlab.com/vanceb/home_automation)

# Merged into broader cctv project - no more updates here

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

~~~ shell
sudo docker run -d \
         --restart=always \
         --name mqtt_cctv \
         --volume /data/cctv/events:/cctv/events \
         --link mosquitto:mosquitto \
         vanceb/mqtt_cctv
~~~

 Needs
 =====

 https://hub.docker.com/r/ansi/mosquitto/
 https://github.com/vanceb/mqtt_gateway
