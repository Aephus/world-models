""" Some data loading utilities """
from os import listdir
from os.path import join, isdir
from tqdm import tqdm
import torch
import numpy as np

class _RolloutDataset(torch.utils.data.Dataset): # pylint: disable=too-few-public-methods
    def __init__(self, root, transform, buffer_size=200, train=True): # pylint: disable=too-many-arguments
        self._transform = transform

        self._files = [
            join(root, sd, ssd)
            for sd in listdir(root) if isdir(join(root, sd))
            for ssd in listdir(join(root, sd))]

        if train:
            self._files = self._files[:-600]
        else:
            self._files = self._files[-600:]

        self._cum_size = None
        self._buffer = None
        self._buffer_fnames = None
        self._buffer_index = 0
        self._buffer_size = buffer_size

    def load_next_buffer(self):
        """ Loads next buffer """
        self._buffer_fnames = self._files[self._buffer_index:self._buffer_index + self._buffer_size]
        self._buffer_index += self._buffer_size
        self._buffer = []
        self._cum_size = [0]

        # progress bar
        pbar = tqdm(total=len(self._buffer_fnames),
                    bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} {postfix}')
        pbar.set_description("Loading file buffer ...")

        for f in self._buffer_fnames:
            with np.load(f) as data:
                self._buffer += [{k: np.copy(v) for k, v in data.items()}]
                self._cum_size += [self._cum_size[-1] +
                                   self._data_per_sequence(data['rewards'].shape[0])]
            pbar.update(1)
        pbar.close()

    def __len__(self):
        # to have a full sequence, you need self.seq_len + 1 elements, as
        # you must produce both an seq_len obs and seq_len next_obs sequences
        return self._cum_size[-1]

    def __getitem__(self, i):
        # binary search through cum_size
        low = 0
        high = len(self._cum_size)
        while low < high:
            mid = (low + high) // 2
            if self._cum_size[mid] > i:
                high = mid
            else:
                cur = mid
                low = mid + 1

        # extract data
        seq_index = i - self._cum_size[cur]
        data = self._buffer[cur]

        return self._get_data(data, seq_index)

    def _get_data(self, data, seq_index):
        pass

    def _data_per_sequence(self, data_length):
        pass


class RolloutSequenceDataset(_RolloutDataset): # pylint: disable=too-few-public-methods
    """ Encapsulates rollouts.

    :args root: root directory of data sequences
    :args seq_len: number of timesteps extracted from each rollout
    :args transform: transformation of the observations
    :args train: if True, train data, else test
    """
    def __init__(self, root, seq_len, transform, buffer_size=200, train=True): # pylint: disable=too-many-arguments
        super().__init__(root, transform, buffer_size, train)
        self._seq_len = seq_len

    def _get_data(self, data, seq_index):
        obs_data = data['observations'][seq_index:seq_index + self._seq_len + 1]
        obs_data = self._transform(obs_data.astype(np.float32))
        obs, next_obs = obs_data[:-1], obs_data[1:]
        action = data['actions'][seq_index+1:seq_index + self._seq_len + 1]
        action = action.astype(np.float32)
        reward, terminal = [data[key][seq_index+1:
                                      seq_index + self._seq_len + 1].astype(np.float32)
                            for key in ('rewards', 'terminals')]
        # data is given in the form
        # (obs, action, reward, terminal, next_obs)
        return obs, action, reward, terminal, next_obs

    def _data_per_sequence(self, data_length):
        return data_length - self._seq_len

class RolloutObservationDataset(_RolloutDataset): # pylint: disable=too-few-public-methods
    """ Encapsulate individual images from rollouts """
    def _data_per_sequence(self, data_length):
        return data_length

    def _get_data(self, data, seq_index):
        return self._transform(data['observations'][seq_index])
