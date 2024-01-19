import time

import cv2
import numpy as np

import multiprocess_handler.config
from multiprocess_handler.multiprocess_handler import ProcessHandler, MarkerSet, SharedFrames
from tracking.test_tracking import print_marker
from frames.frames import Frames
from crop.crop import Crop
from tracking.test_tracking import print_blobs, print_marker, print_position, print_estimated_positions, set_marker_pos


class ImageProcessingHandler:
    def __init__(self, markers_sets: list[MarkerSet], frames: Frames, options, tracking_option):
        self.crops = []
        self.crops_name = [crop['name'] for crop in options['crops']]

        print(self.crops_name)

        for i in range(len(markers_sets)):
            marker_set = markers_sets[i]
            option = options['crops'][i]

            # Init Crop
            crop = Crop(option['area'], frames, marker_set, option['filters'], tracking_option)

            self.crops.append(crop)

    def _process_function(self):
        for i, crop in enumerate(self.crops):
            blobs, positions, estimate_positions = crop.track_markers()
            set_marker_pos(crop.marker_set, positions)

            img = crop.filter.filtered_frame
            img = print_blobs(img, blobs)
            img = print_estimated_positions(img, estimate_positions)
            img = print_marker(img, crop.marker_set)

            cv2.imshow(f"{self.crops_name[i]}", img)
            cv2.waitKey(1)

    def send_process(self, order=1):
        self._process_function()

    def receive_process(self):
        return

    def send_and_receive_process(self, order=1):
        self.send_process(order)
        self.receive_process()

    def end_process(self):
        return


class ProcessImage:
    SHOW_BLOBS = True
    SHOW_ESTIMATION = True
    SHOW_MARKERS = True
    SHOW_CROPS = True

    def __init__(self, config, tracking_options, shared=False):
        # Options
        self.config = config

        # Init Markers
        self.marker_sets = self.init_marker_set(shared)
        # Set offsets for the marker_sets
        for i in range(len(self.marker_sets)):
            self.marker_sets[i].set_offset_pos(config['crops'][i]['area'][:2])

        # Image
        self.path = config['directory']
        self.index = config['start_index']
        color, depth = load_img(self.path, self.index)

        # Frame
        self.frames = None
        if not shared:
            self.frames = Frames(color, depth)
        else:
            self.frames = SharedFrames(color, depth)

        # Process
        if not shared:
            self.process_handler = ImageProcessingHandler(self.marker_sets, self.frames, config, tracking_options)
        else:
            self.process_handler = ProcessHandler(self.marker_sets, self.frames, config, tracking_options)
            self.process_handler.start_process()

    # Init
    def init_marker_set(self, shared):
        set_names = []
        off_sets = []
        marker_names = []
        base_positions = []

        for i in range(len(self.config['crops'])):
            set_names.append(self.config['crops'][i]['name'])
            off_sets.append(self.config['crops'][i]['area'][:2])

            marker_name = []
            base_position = []
            for j in range(len(self.config['crops'][i]['markers'])):
                marker_name.append(self.config['crops'][i]['markers'][j]['name'])
                base_position.append(self.config['crops'][i]['markers'][j]['pos'])

            marker_names.append(marker_name)
            base_positions.append(base_position)

        marker_sets: list[MarkerSet] = []
        for i in range(len(set_names)):
            marker_set = MarkerSet(set_names[i], marker_names[i], shared)
            marker_set.set_markers_pos(base_positions[i])
            marker_set.set_offset_pos(off_sets[i])
            marker_sets.append(marker_set)

        return marker_sets

    # Loading
    def _load_img(self):
        color, depth = load_img(self.path, self.index)
        return color, depth

    def _update_img(self, color, depth):
        if color is None or depth is None:
            return False

        self.frames.set_images(color, depth)

        return True

    # Processing
    def _process_after_loading(self):
        # Update frame
        color, depth = self._load_img()
        if not self._update_img(color, depth):  # If image could not be loaded then skip to the next one
            return False

        # Process image
        self.process_handler.send_and_receive_process()

        return True

    def _process_while_loading(self):
        # Start the processing of the current image
        self.process_handler.send_process()

        # Load next frame
        color, depth = self._load_img()  # If image could not be loaded then skip to the next one

        # Wait for the end of the processing of the image
        self.process_handler.receive_process()

        # # If image could not be loaded then skip to the next one
        return self._update_img(color, depth)

    def process(self):
        avg_load_time = 0
        avg_frame_time = 0
        avg_total_time = 0

        while self.index != self.config['end_index']:
            tik = time.time()

            # Get next image
            self.index += 1

            # Process
            if not self._process_while_loading():
                continue

            avg_total_time += (time.time() - tik)

            cv2.imshow('Main image :', self._get_processed_image())
            if cv2.waitKey(1) == ord('q'):
                break

        self.process_handler.end_process()
        nb_img = self.index - self.config['start_index']
        return avg_load_time / nb_img, avg_frame_time / nb_img, avg_total_time / nb_img

    def _get_processed_image(self):
        img = self.frames.color.copy()
        img = print_marker_sets(img, self.marker_sets)

        return img


def print_marker_sets(frame, marker_sets):
    for i, marker_set in enumerate(marker_sets):
        frame = print_marker(frame, marker_set)

    return frame


def load_img(path, index):
    color_file = path + f"color_{index}.png"
    depth_file = path + f"depth_{index}.png"

    color_image = cv2.flip(cv2.imread(color_file, cv2.COLOR_BGR2RGB), -1)
    depth_image = cv2.flip(cv2.imread(depth_file, cv2.IMREAD_ANYDEPTH), -1)

    return color_image, depth_image