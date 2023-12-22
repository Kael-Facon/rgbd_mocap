import numpy as np

try:
    import pyrealsense2 as rs
except ImportError:
    raise ImportWarning("Cannot use camera: Import of the library pyrealsense2 failed")
    pass
from rgbd_mocap.RgbdImages import RgbdImages


class CameraIntrinsics:
    def __init__(self):
        self.width = None
        self.height = None
        self.fx = None
        self.fy = None
        self.ppx = None
        self.ppy = None
        self.intrinsics_mat = None
        self.model = None
        self.dist_coefficients = None

    def set_intrinsics_from_file(self, fx_fy, ppx_ppy, dist_coefficients, depth_frame):
        self.height = depth_frame.shape[1]
        self.width = depth_frame.shape[0]

        self.fx = fx_fy[0]
        self.fy = fx_fy[1]

        self.ppx = ppx_ppy[0]
        self.ppy = ppx_ppy[1]

        self.dist_coefficients = dist_coefficients
        self.model = rs.distortion.inverse_brown_conrady

        self._set_intrinsics_mat()

    def set_intrinsics(self, intrinsics):
        self.width = intrinsics.width
        self.height = intrinsics.height
        self.ppx = intrinsics.ppx
        self.ppy = intrinsics.ppy
        self.fx = intrinsics.fx
        self.fy = intrinsics.fy
        self.dist_coefficients = intrinsics.coeffs
        self.model = intrinsics.model

        self._set_intrinsics_mat()

    def _set_intrinsics_mat(self):
        self.intrinsics_mat = np.array(
            [
                [self.fx, 0, self.ppx],
                [0, self.fy, self.ppx],
                [0, 0, 1],
            ],
            dtype=float,
        )

    def get_intrinsics(self, model=None):
        _intrinsics = rs.intrinsics()
        _intrinsics.width = self.width
        _intrinsics.height = self.height
        _intrinsics.ppx = self.ppx
        _intrinsics.ppy = self.ppy
        _intrinsics.fx = self.fx
        _intrinsics.fy = self.fy
        _intrinsics.coeffs = self.dist_coefficients
        _intrinsics.model = self.model
        if model:
            _intrinsics.model = model

        return _intrinsics


class CameraConverter:
    """
    CameraConverter class init the camera intrinsics to
    calculate the position of the markers in pixel
    via method 'express_in_pixel' or in meters
    via method 'get_markers_pos_in_meters'.
    """
    def __init__(self, use_camera: bool = False, model=None):
        """
        Init the Camera and its intrinsics. You can determine
        if you are using a camera to get the intrinsics via
        the 'use_camera parameter'. As well, you can change the
        default method of image distortion with 'model' parameter.

        Parameters
        ----------
        use_camera: bool
            True if you get the intrinsics via a connected camera.
            False if you get the intrinsics via configuration files.
        model: rs.intrinsics.property
            Model for distortion to apply on the image for the computation.
        """
        # Camera intrinsics
        self.depth = CameraIntrinsics()
        self.color = CameraIntrinsics()
        self.model = model

        self.set_intrinsics = self._set_intrinsics_from_file
        if use_camera:
            self.set_intrinsics = self._set_intrinsics_from_pipeline

        # Camera extrinsic
        self.depth_to_color = None

    def _set_intrinsics_from_file(self, conf_data, depth_frame):
        """
        Private method.
        Set the Camera intrinsics from file and frame.

        Parameters
        ----------
        conf_data: dict
            Dictionary containing the values to init the intrinsics of the camera.
        depth_frame: np.array
            Depth to determine size of the image.
        """
        self.depth.set_intrinsics_from_file(conf_data["depth_fx_fy"],
                                            conf_data["depth_ppx_ppy"],
                                            conf_data["dist_coeffs_color"],
                                            depth_frame)
        self.color.set_intrinsics_from_file(conf_data["color_fx_fy"],
                                            conf_data["color_ppx_ppy"],
                                            conf_data["dist_coeffs_color"],
                                            depth_frame)

    def _set_intrinsics_from_pipeline(self, pipeline):
        """
        Private method.
        Set the Camera intrinsics from pipeline.

        Parameters
        ----------
        pipeline: Any
            Pipeline linked to the connected camera.
        """
        _intrinsics = (
            pipeline.get_active_profile()
            .get_stream(rs.stream.depth)
            .as_video_stream_profile()
            .get_intrinsics()
        )

        self.depth.set_intrinsics(_intrinsics)
        self.color.set_intrinsics(_intrinsics)

    def express_in_pixel(self, marker_pos_in_meters):
        """
        Get the intrinsics and compute the markers positions
        in meters to get the markers positions in pixel.\

        Parameters
        ----------
        marker_pos_in_meters: np.array
            Markers positions in meters.

        Returns
        -------
        np.array
        """
        _intrinsics = self.depth.get_intrinsics(self.model)

        markers_in_pixels = self._compute_markers(_intrinsics, marker_pos_in_meters, rs.rs2_project_point_to_pixel)

        return markers_in_pixels

    def get_markers_pos_in_meter(self, marker_pos_in_pixel=None, method: callable = None):
        """
        Get the intrinsics and compute the markers positions
        in pixels to get the markers positions in meters.
        If both parameters are set then the given
        'marker_pos_in_pixel' override the one get from
        the method.

        Parameters
        ----------
        marker_pos_in_pixel: np.array
            Markers positions in meters.
        method: callable
            Method to get markers position (Either RgbdImages.get_global_markers_pos or
            RgbdImages.get_merged_global_markers_pos methods)

        Returns
        -------
        np.array
        """
        if marker_pos_in_pixel is None and method is None:
            raise ValueError("""[Camera] Cannot get markers position in meters:
             arguments 'marker_pos_in_pixel' and 'method' are None""")

        if method is not None and (RgbdImages.get_global_markers_pos == method or
                                   RgbdImages.get_merged_global_markers_pos == method):
            raise ValueError(f"""[Camera] Cannot get markers position in meters: argument 'method' is not a valid.
            Valid methods are: {RgbdImages.get_global_markers_pos} and {RgbdImages.get_merged_global_markers_pos}""")

        if marker_pos_in_pixel is None:
            marker_pos_in_pixel, markers_names, occlusions, reliability = method()  # Call get_global_markers_pos or
                                                                                    # get_merged_global_markers_pos
        elif method is None:
            markers_names, occlusions, reliability = None, None, 0
        else:
            _, markers_names, occlusions, reliability = method()

        _intrinsics = self.depth.get_intrinsics(self.model)
        markers_in_meters = self._compute_markers(_intrinsics, marker_pos_in_pixel, rs.rs2_deproject_pixel_to_point)

        return markers_in_meters, markers_names, occlusions, reliability

    @staticmethod
    def _compute_markers(intrinsics, marker_pos, method,):
        """
        Private method.
        Compute the markers positions with the given method and intrinsics.
        For positions in meters to pixels use rs.rs2_project_point_to_pixel
        For positions in pixels to meters use rs.rs2_deproject_pixel_to_point

        Parameters
        ----------
        intrinsics: rs.intrinsics
            Camera intrinsics.
        marker_pos:
            Markers positions.
        method:
            Method to compute markers positions.

        Returns
        -------
        np.array
        """
        markers = np.zeros_like(marker_pos)

        for m in range(marker_pos.shape[1]):
            markers[:2, m] = method(
                intrinsics, [marker_pos[0, m], marker_pos[1, m], marker_pos[2, m]]
            )
        return markers
