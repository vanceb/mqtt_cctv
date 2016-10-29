FROM python:3-onbuild

# Update image and get avconv package
RUN apt-get update && apt-get -y install libav-tools

# Run our python script in the container
CMD [ "python", "./event-capture.py"]
