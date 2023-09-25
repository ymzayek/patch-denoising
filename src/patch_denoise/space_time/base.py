"""Base Structure for patch-based denoising on spatio-temporal dimension."""
import abc
import warnings
import numpy as np
from tqdm.auto import tqdm
import torch
import torch.nn as nn
import torch.nn.functional as F
from .._docs import fill_doc

from .utils import get_patch_locs


@fill_doc
class BaseSpaceTimeDenoiser(abc.ABC):
    """
    Base Class for Patch-based denoising methods for dynamical data.

    Parameters
    ----------
    $patch_config
    """

    def __init__(self, patch_shape, patch_overlap, recombination="weighted"):
        self.p_shape = patch_shape
        self.p_ovl = patch_overlap

        if recombination not in ["weighted", "average", "center"]:
            raise ValueError(
                "recombination must be one of 'weighted', 'average', 'center'"
            )

        self.recombination = recombination

        self.input_denoising_kwargs = dict()

    @fill_doc
    def denoise(self, input_data, mask=None, mask_threshold=50, progbar=None):
        """Denoise the input_data, according to mask.

        Patches are extracted sequentially and process by the implemented
        `_patch_processing` function.
        Only patches which have at least a voxel in the mask ROI are processed.

        Parameters
        ----------
        $input_config
        $mask_config

        Returns
        -------
        $denoise_return
        """
        data_shape = input_data.shape
        output_data = np.zeros_like(input_data)
        rank_map = np.zeros(data_shape[:-1], dtype=np.int32)
        # Create Default mask
        if mask is None:
            process_mask = np.full(data_shape[:-1], True)
        else:
            process_mask = np.copy(mask)
        patch_shape, patch_overlap = self.__get_patch_param(data_shape)

        patch_size = np.prod(patch_shape)
        input_data_reshaped = torch.from_numpy(input_data.reshape(input_data.shape[-1], input_data.shape[0], input_data.shape[1], input_data.shape[2]))

        print(input_data_reshaped.shape)

        _, c, h, w = input_data_reshaped.shape
        kc, kh, kw = patch_shape  # kernel size
        dc, dh, dw = np.repeat(patch_shape[0] - patch_overlap[0], 3)
        pc = int(np.ceil(c/kc) * kc - c)
        ph = int(np.ceil(h/kh) * kh - h)
        pw = int(np.ceil(w/kw) * kw - w)

        input_data_reshaped = F.pad(input=input_data_reshaped, pad=(0, pw, 0, ph, 0, pc), mode='constant', value=0)

        patches = input_data_reshaped.unfold(1, kc, dc).unfold(2, kh, dh).unfold(3, kw, dw)
        unfold_shape = patches.size()
        patches = patches.contiguous().view(patches.size(0), -1, kc, kh, kw)
        print(patches.shape)

        # Reshape back
        # patches_orig = patches.view(unfold_shape)
        # print(patches_orig.shape)
        # print(unfold_shape)
        # output_h = unfold_shape[0] * unfold_shape[2]
        # output_w = unfold_shape[1] * unfold_shape[3]
        # patches_orig = patches_orig.permute(0, 2, 1, 3).contiguous()
        # patches_orig = patches_orig.view(output_h, output_w)
        # print(patches_orig.shape)
        # exit(0)
        # exit(0)
        if self.recombination == "center":
            patch_center = (
                *(slice(ps // 2, ps // 2 + 1) for ps in patch_shape),
                slice(None, None, None),
            )
        patchs_weight = np.zeros(data_shape[:-1], np.float32)
        noise_std_estimate = np.zeros(data_shape[:-1], dtype=np.float32)

        # discard useless patches
        patch_locs = get_patch_locs(patch_shape, patch_overlap, data_shape[:-1])
        get_it = np.zeros(len(patch_locs), dtype=bool)

        for i, patch_tl in enumerate(patch_locs):
            patch_slice = tuple(
                slice(tl, tl + ps) for tl, ps in zip(patch_tl, patch_shape)
            )
            if 100 * np.sum(process_mask[patch_slice]) / patch_size > mask_threshold:
                get_it[i] = True

        print("Denoise {:.2f}% patches".format(100 * np.sum(get_it) / len(patch_locs)))
        print(f"Before:{patch_locs.shape}")
        patch_locs = np.ascontiguousarray(patch_locs[get_it])

        if progbar is None:
            progbar = tqdm(total=len(patch_locs))
        elif progbar is not False:
            progbar.reset(total=len(patch_locs))
        # print(patch_locs)
        print(patch_locs.shape)
        exit(0)
        for patch_tl in patch_locs:
            print(patch_tl)
            # exit(0)
            patch_slice = tuple(
                slice(tl, tl + ps) for tl, ps in zip(patch_tl, patch_shape)
            )
            process_mask[patch_slice] = 1
            # building the casoratti matrix
            patch = np.reshape(input_data[patch_slice], (-1, input_data.shape[-1]))
            print(patch_locs.shape)
            print(patch.shape)
            exit(0)
            # Replace all nan by mean value of patch.
            # FIXME this behaviour should be documented
            # And ideally choosen by the user.

            patch[np.isnan(patch)] = np.mean(patch)
            p_denoise, maxidx, noise_var = self._patch_processing(
                patch,
                patch_slice=patch_slice,
                **self.input_denoising_kwargs,
            )

            p_denoise = np.reshape(p_denoise, (*patch_shape, -1))
            patch_center_img = tuple(
                ptl + ps // 2 for ptl, ps in zip(patch_tl, patch_shape)
            )
            if self.recombination == "center":
                output_data[patch_center_img] = p_denoise[patch_center]
                noise_std_estimate[patch_center_img] += noise_var
            elif self.recombination == "weighted":
                theta = 1 / (2 + maxidx)
                output_data[patch_slice] += p_denoise * theta
                patchs_weight[patch_slice] += theta
            elif self.recombination == "average":
                output_data[patch_slice] += p_denoise
                patchs_weight[patch_slice] += 1
            else:
                raise ValueError(
                    "recombination must be one of 'weighted', 'average', 'center'"
                )
            if not np.isnan(noise_var):
                noise_std_estimate[patch_slice] += noise_var
            # the top left corner of the patch is used as id for the patch.
            rank_map[patch_center_img] = maxidx
            if progbar:
                progbar.update()
        # Averaging the overlapping pixels.
        # this is only required for averaging recombinations.
        if self.recombination in ["average", "weighted"]:
            output_data /= patchs_weight[..., None]
            noise_std_estimate /= patchs_weight

        output_data[~process_mask] = 0

        return output_data, patchs_weight, noise_std_estimate, rank_map

    @abc.abstractmethod
    def _patch_processing(self, patch, patch_slice=None, **kwargs):
        """Process a patch.

        Implemented by child classes.
        """

    def __get_patch_param(self, data_shape):
        """Return tuple for patch_shape and patch_overlap.

        It works from whatever the  input format was (int or list).
        This method also ensure that the patch will provide tall and skinny matrices.
        """
        pp = [None, None]
        for i, attr in enumerate(["p_shape", "p_ovl"]):
            p = getattr(self, attr)
            if isinstance(p, list):
                p = tuple(p)
            elif isinstance(p, (int, np.integer)):
                p = (p,) * (len(data_shape) - 1)
            pp[i] = p
        if np.prod(pp[0]) < data_shape[-1]:
            warnings.warn(
                f"the number of voxel in patch ({np.prod(pp[0])}) is smaller than the"
                f" last dimension ({data_shape[-1]}), this makes an ill-conditioned"
                "matrix for SVD.",
                stacklevel=2,
            )
        return tuple(pp)
