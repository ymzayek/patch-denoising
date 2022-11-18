"""Binding for ModOpt Package."""

import numpy as np
from modopt.opt.proximity import ProximityParent

from .utils import DENOISER_MAP


class LLRDenoiserOperator(ProximityParent):
    """Proximal Operator drop-in replacement using local low rank denoising.

    Parameters
    ----------
    denoiser: str
        name of the denoising method.
    patch_shape: tuple
        The patch shape
    patch_overlap: tuple
        the overlap of each pixel
    mask: numpy.ndarray
        A boolean array, defining a ROI in the volume. Only patch with voxels in the ROI
        will be processed.
    mask_threshold: int
        percentage of the path that has to be in the mask so that the patch is processed.
        if mask_threshold = -1, all the patch are processed, if mask_threshold=100, all
        the voxels of the patch needs to be in the mask
    """

    def __init__(
        self,
        denoiser,
        patch_shape,
        patch_overlap,
        mask=None,
        mask_threshold=-1,
        **kwargs,
    ):
        self._denoiser = DENOISER_MAP["denoiser"]
        self._params = dict(
            patch_shape=patch_shape,
            patch_overlap=patch_overlap,
            mask=mask,
            mask_threshold=mask_threshold,
        )

        self.op = self._op_method
        self.cost = lambda *args, **kwargs: np.NaN

    def _op_method(self, data, **kwargs):
        run_kwargs = self._params.copy()
        run_kwargs.update(kwargs)
        return self._denoiser(data, **run_kwargs)[0]