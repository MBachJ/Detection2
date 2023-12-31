##################################################################################################################################
######## Webcam Object Detection Using Tensorflow-trained Classifier #########
#
# Author: Evan Juras
# Date: 10/27/19
# Description: 
# This program uses a TensorFlow Lite model to perform object detection on a live webcam
# feed. It draws boxes and scores around the objects of interest in each frame from the
# webcam. To improve FPS, the webcam object runs in a separate thread from the main program.
# This script will work with either a Picamera or regular USB webcam.
#
# This code is based off the TensorFlow Lite image classification example at:
# https://github.com/tensorflow/tensorflow/blob/master/tensorflow/lite/examples/python/label_image.py
#
# I added my own method of drawing boxes and labels using OpenCV.
####################################################################################################################################

# Dette er hovedprogrammet for objektedeteksjon, programmet er i førsteomgang utviklet av The Tensorflow Authors.
# Videre er koden modifiser av Evan Juares, som beskrevet i teksten over.

#######################################################################################################################################################################################

# Koden er også videreutviklet av oss i denne oppgaven, for å få til flere funksjoner som lagring av bilder og deteksjonsdata. Endringene vi har gjort er godt markert med kommentarer.

# Ved spørsmål, kontakt: magnuspolsroed@gmail.com

########################################################################################################################################################################################


# Import packages
import os
import argparse
import cv2
import numpy as np
import sys
import time
from threading import Thread
from datetime import datetime
import importlib.util

# Define VideoStream class to handle streaming of video from webcam in separate processing thread
# Source - Adrian Rosebrock, PyImageSearch: https://www.pyimagesearch.com/2015/12/28/increasing-raspberry-pi-fps-with-python-and-opencv/
class VideoStream:
    """Camera object that controls video streaming from the Picamera"""
    def __init__(self,resolution=(640,480),framerate=30):
        # Initialize the PiCamera and the camera image stream
        self.stream = cv2.VideoCapture(0)
        ret = self.stream.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        ret = self.stream.set(3,resolution[0])
        ret = self.stream.set(4,resolution[1])
            
        # Read first frame from the stream
        (self.grabbed, self.frame) = self.stream.read()

	# Variable to control when the camera is stopped
        self.stopped = False

    def start(self):
	# Start the thread that reads frames from the video stream
        Thread(target=self.update,args=()).start()
        return self

    def update(self):
        # Keep looping indefinitely until the thread is stopped
        while True:
            # If the camera is stopped, stop the thread
            if self.stopped:
                # Close camera resources
                self.stream.release()
                return

            # Otherwise, grab the next frame from the stream
            (self.grabbed, self.frame) = self.stream.read()

    def read(self):
	# Return the most recent frame
        return self.frame

    def stop(self):
	# Indicate that the camera and thread should be stopped
        self.stopped = True

# Define and parse input arguments
parser = argparse.ArgumentParser()
parser.add_argument('--modeldir', help='Folder the .tflite file is located in',
                    required=True)
parser.add_argument('--graph', help='Name of the .tflite file, if different than detect.tflite',
                    default='detect.tflite')
parser.add_argument('--labels', help='Name of the labelmap file, if different than labelmap.txt',
                    default='labelmap.txt')
parser.add_argument('--threshold', help='Minimum confidence threshold for displaying detected objects',
                    default=0.5)
parser.add_argument('--resolution', help='Desired webcam resolution in WxH. If the webcam does not support the resolution entered, errors may occur.',
                    default='1280x720')
parser.add_argument('--edgetpu', help='Use Coral Edge TPU Accelerator to speed up detection',
                    action='store_true')

args = parser.parse_args()

MODEL_NAME = args.modeldir
GRAPH_NAME = args.graph
LABELMAP_NAME = args.labels
min_conf_threshold = float(args.threshold)
resW, resH = args.resolution.split('x')
imW, imH = int(resW), int(resH)
use_TPU = args.edgetpu

# Import TensorFlow libraries
# If tflite_runtime is installed, import interpreter from tflite_runtime, else import from regular tensorflow
# If using Coral Edge TPU, import the load_delegate library
pkg = importlib.util.find_spec('tflite_runtime')
if pkg:
    from tflite_runtime.interpreter import Interpreter
    if use_TPU:
        from tflite_runtime.interpreter import load_delegate
else:
    from tensorflow.lite.python.interpreter import Interpreter
    if use_TPU:
        from tensorflow.lite.python.interpreter import load_delegate

# If using Edge TPU, assign filename for Edge TPU model
if use_TPU:
    # If user has specified the name of the .tflite file, use that name, otherwise use default 'edgetpu.tflite'
    if (GRAPH_NAME == 'detect.tflite'):
        GRAPH_NAME = 'edgetpu.tflite'       

# Get path to current working directory
CWD_PATH = os.getcwd()

# Path to .tflite file, which contains the model that is used for object detection
PATH_TO_CKPT = os.path.join(CWD_PATH,MODEL_NAME,GRAPH_NAME)

# Path to label map file
PATH_TO_LABELS = os.path.join(CWD_PATH,MODEL_NAME,LABELMAP_NAME)

# Load the label map
with open(PATH_TO_LABELS, 'r') as f:
    labels = [line.strip() for line in f.readlines()]

# Have to do a weird fix for label map if using the COCO "starter model" from
# https://www.tensorflow.org/lite/models/object_detection/overview
# First label is '???', which has to be removed.
if labels[0] == '???':
    del(labels[0])

# Load the Tensorflow Lite model.
# If using Edge TPU, use special load_delegate argument
if use_TPU:
    interpreter = Interpreter(model_path=PATH_TO_CKPT,
                              experimental_delegates=[load_delegate('libedgetpu.so.1.0')])
    print(PATH_TO_CKPT)
else:
    interpreter = Interpreter(model_path=PATH_TO_CKPT)

interpreter.allocate_tensors()

# Get model details
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()
height = input_details[0]['shape'][1]
width = input_details[0]['shape'][2]

floating_model = (input_details[0]['dtype'] == np.float32)

input_mean = 127.5
input_std = 127.5

# Check output layer name to determine if this model was created with TF2 or TF1,
# because outputs are ordered differently for TF2 and TF1 models
outname = output_details[0]['name']

if ('StatefulPartitionedCall' in outname): # This is a TF2 model
    boxes_idx, classes_idx, scores_idx = 1, 3, 0
else: # This is a TF1 model
    boxes_idx, classes_idx, scores_idx = 0, 1, 2

# Initialize frame rate calculation
frame_rate_calc = 1
freq = cv2.getTickFrequency()

# Initialize video stream
videostream = VideoStream(resolution=(imW,imH),framerate=30).start()
time.sleep(1)

##############################################################################################################################################################
# Kode lagt til for dette prosjektet

last_saved_timestamp = None #variabel for å ta tiden av når man skal lagre bilder
last_directory_timestamp = None #variabel for opprettelse av mappe

##############################################################################################################################################################

#for frame1 in camera.capture_continuous(rawCapture, format="bgr",use_video_port=True):
while True:

    # Start timer (for calculating frame rate)
    t1 = cv2.getTickCount()

    # Grab frame from video stream
    frame1 = videostream.read()

    # Acquire frame and resize to expected shape [1xHxWx3]
    frame = frame1.copy()
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frame_resized = cv2.resize(frame_rgb, (width, height))
    input_data = np.expand_dims(frame_resized, axis=0)

    # Normalize pixel values if using a floating model (i.e. if model is non-quantized)
    if floating_model:
        input_data = (np.float32(input_data) - input_mean) / input_std

    # Perform the actual detection by running the model with the image as input
    interpreter.set_tensor(input_details[0]['index'],input_data)
    interpreter.invoke()

    # Retrieve detection results
    boxes = interpreter.get_tensor(output_details[boxes_idx]['index'])[0] # Bounding box coordinates of detected objects
    classes = interpreter.get_tensor(output_details[classes_idx]['index'])[0] # Class index of detected objects
    scores = interpreter.get_tensor(output_details[scores_idx]['index'])[0] # Confidence of detected objects
    
    # Draw framerate in corner of frame
    cv2.putText(frame,'FPS: {0:.2f}'.format(frame_rate_calc),(30,50),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,0),2,cv2.LINE_AA)

    # Loop over all detections and draw detection box if confidence is above minimum threshold
    for i in range(len(scores)):
        if ((scores[i] > min_conf_threshold) and (scores[i] <= 1.0)):

            ##################################################################################################################
            # Kode lagt til for dette prosjektet
            
            frame_copy = frame.copy() #Tar en kopi av bildet uten ramme rundt objektet
            
            ##################################################################################################################
            
            # Get bounding box coordinates and draw box
            # Interpreter can return coordinates that are outside of image dimensions, need to force them to be within image using max() and min()
            ymin = int(max(1,(boxes[i][0] * imH)))
            xmin = int(max(1,(boxes[i][1] * imW)))
            ymax = int(min(imH,(boxes[i][2] * imH)))
            xmax = int(min(imW,(boxes[i][3] * imW)))
            
            cv2.rectangle(frame, (xmin,ymin), (xmax,ymax), (10, 255, 0), 2)

            # Draw label
            object_name = labels[int(classes[i])] # Look up object name from "labels" array using class index
            label = '%s: %d%%' % (object_name, int(scores[i]*100)) # Example: 'person: 72%'
            labelSize, baseLine = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2) # Get font size
            label_ymin = max(ymin, labelSize[1] + 10) # Make sure not to draw label too close to top of window
            cv2.rectangle(frame, (xmin, label_ymin-labelSize[1]-10), (xmin+labelSize[0], label_ymin+baseLine-10), (255, 255, 255), cv2.FILLED) # Draw white box to put label text in
            cv2.putText(frame, label, (xmin, label_ymin-7), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2) # Draw label text

####################################################################################################################################################################	   
            # Kode lagt til for dette prosjektet
            
            # Her er det laget kode for å lagre informasjon om en deteksjon
            # Hvis objektet er 'boat' og sikkerheten er over 50% skal det lagres bilder
            if object_name == 'boat' and scores[i] >= 0.3:
                current_timestamp = datetime.now()
                
                if last_directory_timestamp is None or (current_timestamp - last_directory_timestamp).seconds >= 120:
                    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')  # år, mnd, dag, timer, min
                    # Find directory for this detection
                    directory_detection = f"Directory_for_detection_{timestamp}"
                    # Defining path to this directory
                    parent_dir_detection = "/home/berpol/deteksjon2/Fartøys_deteksjon/deteksjoner"
                    # Coupling the path and the directory together
                    path_dir_run = os.path.join(parent_dir_detection, directory_detection)
    
                    # Create the directory
                    if not os.path.exists(path_dir_run):
                        os.mkdir(path_dir_run)
                    # Oppdater tidspunktet for når den siste mappen ble laget
                    last_directory_timestamp = current_timestamp
                
                
                # Hvis det er den første deteksjonen, eller det har gått 5 sekunder siden siste lagrede deteksjon
                if last_saved_timestamp is None or (current_timestamp - last_saved_timestamp).seconds >= 2:
                    image_timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')  # år, mnd, dag, timer, min, sek
                    filename = f"detected_ship_{image_timestamp}.jpg"  # Bilde filen skal også få navn etter tidsunktet det ble tatt
                    filename_without_box = f"detected_ship_{image_timestamp}_WithoutBOX.jpg"  # Bildey uten box skal også få et navn
                    filepath = os.path.join(path_dir_run, filename)  # Hvor filen skal lagres
                    filepath_without_box = os.path.join(path_dir_run, filename_without_box) # Hvor bilde filen uten box lagres
                    cv2.imwrite(filepath_without_box, frame_copy) # Lagrer bildet uten box
                    cv2.imwrite(filepath, frame) # Lagrer bilder med box
    
                    # Define the name of the new file
                    name_of_file = "Documented_detection_data.txt"
                    # Coupling the name of the document and the path to parent directory
                    complete_name = os.path.join(path_dir_run, name_of_file)
                    
                    boat_coords = (60.403, 5.272) #Her er koordinatene som er funnet midt i bildet, som blir gitt til objektet. MÅ endre når kameraet bytter posisjon
                    
                    # Append to the file
                    with open(complete_name, "a") as f:
                        # Write in the data we want to log
                        f.write(image_timestamp + "\t" + object_name + "\t" + "{:.2f}".format(scores[i]) + "\t" + filename_without_box + "/" + filename + "\tBox coordinates: " + "[UPPER LEFT(" + str(xmin) + ", " + str(ymin) + "), " + "LOWER RIGHT(" + str(xmax) + ", " + str(ymax) + ")]" + "\t" + "Coords: " + str(boat_coords) + "\n")

                    # Oppdater tiden for siste lagrede deteksjon
                    last_saved_timestamp = current_timestamp

#######################################################################################################################################################################

    # All the results have been drawn on the frame, so it's time to display it.
    cv2.imshow('Object detector', frame)

    # Calculate framerate
    t2 = cv2.getTickCount()
    time1 = (t2-t1)/freq
    frame_rate_calc= 1/time1

    # Press 'q' to quit
    if cv2.waitKey(1) == ord('q'):
        break

# Clean up
cv2.destroyAllWindows()
videostream.stop()
