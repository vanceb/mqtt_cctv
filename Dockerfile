FROM python:3-onbuild

# Update image and get avconv package
RUN apt-get update && apt-get -y install libav-tools

# Add any necessary python packages
ADD requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# Copy our files across
ADD . /code
WORKDIR /code

# Run our python script in the container
CMD [ "python", "./event-capture.py"]
