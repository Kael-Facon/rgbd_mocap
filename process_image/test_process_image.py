import time

import cv2
import numpy as np

from process_image import ProcessImage
import multiprocess_handler


tracking_options = {
        "naive": False,
        "kalman": True,
        "optical_flow": True,
    }


if __name__ == '__main__':
    # Init
    PI = ProcessImage(multiprocess_handler.config.config, tracking_options, shared=False)

    # Run
    load_time, frame_time, tot_time = PI.process()

    print("Everything's fine !")
    print('Average load time :', load_time)
    print('Average computation time :', frame_time)
    print('Average total time :', tot_time)