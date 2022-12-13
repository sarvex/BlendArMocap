'''
Copyright (C) cgtinker, cgtinker.com, hello@cgtinker.com

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import logging
from .cgt_detection import provide_face_data, provide_pose_data, provide_hand_data
from .cgt_detection import provide_holistic_data, realtime_data_provider_interface, stream
from .cgt_freemocap import fm_session_loader
from .cgt_patterns import events
from .cgt_bridge import bpy_hand_bridge, bpy_pose_bridge, bpy_face_bridge, bpy_bridge_interface, print_bridge
from .cgt_processing import hand_processing, pose_processing, face_processing, processor_interface


class RealtimeDataProcessingManager:
    target: str = ""
    logger = logging.getLogger('BlendArMocap')
    realtime_data_provider: realtime_data_provider_interface = None
    bridge: bpy_bridge_interface = None
    processor: processor_interface = None

    # bridge to assign processed results to blender
    bpy_bridges = {
        "HAND":     bpy_hand_bridge.BpyHandBridge,
        "POSE":     bpy_pose_bridge.BpyPoseBridge,
        "FACE":     bpy_face_bridge.BpyFaceBridge,
        "HOLISTIC": [bpy_hand_bridge.BpyHandBridge, bpy_face_bridge.BpyFaceBridge, bpy_pose_bridge.BpyPoseBridge],
        "FREEMOCAP": [bpy_hand_bridge.BpyHandBridge, bpy_face_bridge.BpyFaceBridge, bpy_pose_bridge.BpyPoseBridge],
    }

    # provider mediapipe output data from vid/stream/freemocap
    data_providers = {
        "HAND":     provide_hand_data.HandDetector,
        "POSE":     provide_pose_data.PoseDetector,
        "FACE":     provide_face_data.FaceDetector,
        "HOLISTIC": provide_holistic_data.HolisticDetector,
        "FREEMOCAP": fm_session_loader.FreemocapLoader,
    }

    # process mediapipe data and add 3D rotations
    processor_types = {
        "HAND": hand_processing.HandProcessor,
        "POSE": pose_processing.PoseProcessor,
        "FACE": face_processing.FaceProcessor,
        "HOLISTIC": [hand_processing.HandProcessor, face_processing.FaceProcessor, pose_processing.PoseProcessor],
        "FREEMOCAP": [hand_processing.HandProcessor, face_processing.FaceProcessor, pose_processing.PoseProcessor],
    }

    # mapping options to pipe processed results
    observers = {
        "BPY":          events.BpyUpdateReceiver,
        "RAW":          events.PrintRawDataUpdate,
        "DEBUG":        events.DriverDebug,   # may doesn't while working with mathutils
        "BPY_HOLISTIC": events.HolisticBpyUpdateReceiver,
        "BPY_FREEMOCAP": events.HolisticBpyUpdateReceiver,
        "DEBUG_HOLISTIC": events.HolisticDriverDebug
    }

    def __init__(self, target: str = "HAND", bridge_type: str = "BPY"):
        """ Initialize a detection handler using a detection target type and a bridge type.
            A mediapipe model handles the detection in a cv2 stream. The data is getting processed
            for blender. It's also possible to print data using the print bridges.
            :param target: type of ['HAND', 'POSE', 'FACE', 'HOLISTIC']
            :param bridge_type: type of ['BPY', 'PROCESSED', 'RAW']
            """
        self.logger.info(f"Setting up {self.__class__.__name__}({target}, {bridge_type})")
        self.realtime_data_provider = self.data_providers[target]
        self.processor: processor_interface.DataProcessor = self.processor_types[target]
        if bridge_type == "RAW":
            self.processor = None

        # assign or print data (processed printing only available for location and scale data)
        if bridge_type == "BPY":
            self.bridge = self.bpy_bridges[target]
        else:
            self.bridge = print_bridge.PrintBridge

        # observers input and feeds processor with detection results
        self.listener = events.UpdateListener()
        if target == "HOLISTIC":
            bridge_type += "_"
            bridge_type += target
        if target == "FREEMOCAP":
            bridge_type = "BPY_FREEMOCAP"

        self.observer = self.observers[bridge_type]

    def init_detector(self, capture_input=None, dimension: str = "sd", stream_backend: int = 0,
                      frame_start: int = 0, key_step: int = 1, input_type: int = 1):
        """ Init stream and detector using preselected detection type.
            :param capture_input: cap input for cv2 (b.e. int or filepath)
            :param dimension: dimensions of the cv2 stream ["sd", "hd", "fhd"]
            :param stream_backend: cv2default or cv2cap_dshow [0, 1]
            :param frame_start: key frame start in blender timeline
            :param key_step: keyframe step for capture results
            :param input_type: 1: "movie" or 0: "stream" input
            :return: returns nothing: """
        # initialize the detector
        self.realtime_data_provider = self.realtime_data_provider(frame_start=frame_start, key_step=key_step, input_type=input_type)
        if input_type == 2: # FreeMocap
            self.realtime_data_provider.initialize_model()
            return

        # stream capture dimensions
        dimensions_dict = {
            "sd":  [720, 480],
            "hd":  [1240, 720],
            "fhd": [1920, 1080]
        }
        dim = dimensions_dict[dimension]

        # default webcam slot
        if capture_input is None:
            capture_input = 0

        # init tracking handler targets
        self.realtime_data_provider.stream = stream.Webcam(
            capture_input=capture_input, width=dim[0], height=dim[1], backend=stream_backend
        )

        # stop if opening stream failed
        if not self.realtime_data_provider.stream.capture.isOpened():
            raise IOError("Initializing Detector failed.")

        # initialize mediapipe model
        self.realtime_data_provider.initialize_model()

    def init_bridge(self):
        """ Initialize bridge to print raw data / to blender. """
        if self.processor is None:
            self.realtime_data_provider.init_bridge(self.observer(), self.listener)
            return

        # is holistic
        elif type(self.processor) is list:
            # holistic
            _processor = self.processor.copy()
            _processor[0] = _processor[0](self.bridge[0])
            _processor[1] = _processor[1](self.bridge[1])
            _processor[2] = _processor[2](self.bridge[2])
            _observer = self.observer(_processor)

            self.realtime_data_provider.init_bridge(_observer, self.listener)

        # is face, pose or hand
        else:
            _processor = self.processor(self.bridge)
            _observer = self.observer(_processor)
            self.realtime_data_provider.init_bridge(_observer, self.listener)

    def __del__(self):
        del self.realtime_data_provider


def main():
    handler = RealtimeDataProcessingManager("FACE", "DEBUG")
    handler.init_detector(0, "sd", 0, 0, 0, 0)
    handler.init_bridge()

    for _ in range(15):
        handler.realtime_data_provider.frame_detection_data()

    del handler


if __name__ == '__main__':
    main()
