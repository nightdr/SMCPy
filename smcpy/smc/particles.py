'''
Notices:
Copyright 2018 United States Government as represented by the Administrator of
the National Aeronautics and Space Administration. No copyright is claimed in
the United States under Title 17, U.S. Code. All Other Rights Reserved.

Disclaimers
No Warranty: THE SUBJECT SOFTWARE IS PROVIDED "AS IS" WITHOUT ANY WARRANTY OF
ANY KIND, EITHER EXPRessED, IMPLIED, OR STATUTORY, INCLUDING, BUT NOT LIMITED
TO, ANY WARRANTY THAT THE SUBJECT SOFTWARE WILL CONFORM TO SPECIFICATIONS, ANY
IMPLIED WARRANTIES OF MERCHANTABILITY, FITNess FOR A PARTICULAR PURPOSE, OR
FREEDOM FROM INFRINGEMENT, ANY WARRANTY THAT THE SUBJECT SOFTWARE WILL BE ERROR
FREE, OR ANY WARRANTY THAT DOCUMENTATION, IF PROVIDED, WILL CONFORM TO THE
SUBJECT SOFTWARE. THIS AGREEMENT DOES NOT, IN ANY MANNER, CONSTITUTE AN
ENDORSEMENT BY GOVERNMENT AGENCY OR ANY PRIOR RECIPIENT OF ANY RESULTS,
RESULTING DESIGNS, HARDWARE, SOFTWARE PRODUCTS OR ANY OTHER APPLICATIONS
RESULTING FROM USE OF THE SUBJECT SOFTWARE.  FURTHER, GOVERNMENT AGENCY
DISCLAIMS ALL WARRANTIES AND LIABILITIES REGARDING THIRD-PARTY SOFTWARE, IF
PRESENT IN THE ORIGINAL SOFTWARE, AND DISTRIBUTES IT "AS IS."

Waiver and Indemnity:  RECIPIENT AGREES TO WAIVE ANY AND ALL CLAIMS AGAINST THE
UNITED STATES GOVERNMENT, ITS CONTRACTORS AND SUBCONTRACTORS, AS WELL AS ANY
PRIOR RECIPIENT.  IF RECIPIENT'S USE OF THE SUBJECT SOFTWARE RESULTS IN ANY
LIABILITIES, DEMANDS, DAMAGES, EXPENSES OR LOSSES ARISING FROM SUCH USE,
INCLUDING ANY DAMAGES FROM PRODUCTS BASED ON, OR RESULTING FROM, RECIPIENT'S
USE OF THE SUBJECT SOFTWARE, RECIPIENT SHALL INDEMNIFY AND HOLD HARMLess THE
UNITED STATES GOVERNMENT, ITS CONTRACTORS AND SUBCONTRACTORS, AS WELL AS ANY
PRIOR RECIPIENT, TO THE EXTENT PERMITTED BY LAW.  RECIPIENT'S SOLE REMEDY FOR
ANY SUCH MATTER SHALL BE THE IMMEDIATE, UNILATERAL TERMINATION OF THIS
AGREEMENT.
'''

import importlib
import numpy as np
import copy
import functools
import warnings
from smcpy.utils.checks import Checks


def _mpi_decorator(func):

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        """
        Detects whether multiple processors are available and sets
        self.number_CPUs and self.cpu_rank accordingly. Only calls decorated
        function using rank 0.
        """
        try:
            importlib.find_module('mpi4py')

            from mpi4py import MPI
            comm = MPI.COMM_WORLD.Clone()

            size = comm.size
            rank = comm.rank
            comm = comm

        except ImportError:

            size = 1
            rank = 0
            comm = SingleRankComm()

        if rank == 0:
            func(self, *args, **kwargs)

    return wrapper


def package_for_user(func):

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        """
        Packages array output in a dictionary with keys = parameter names and
        values = array columns UNLESS kwarg package=False is passed to the
        decorated function.
        """
        if 'package' in kwargs.keys() and kwargs['package'] == False:
            return func(self)

        else:
            outputs = func(self, *args, **kwargs)
            names = self.param_names
            return {name: output for name, output in zip(names, outputs)}

    return wrapper



class Particles(Checks):
    '''
    A container for particles during sequential monte carlo (SMC) sampling.
    '''

    def __init__(self, params, log_likes, log_weights):
        '''
        :param params: model parameters; keys are parameter names and values
            are particle values
        :type params: dictionary of 1D arrays or lists
        :param log_likes: natural log of particle likelihoods
        :type log_likes: 1D array or list
        :param log_weights: natural log of particle weights; weights will be
            automatically normalized when set to avoid potential misuse
        :type log_weights: 1D array or list
        '''
        self._param_names = None
        self._num_particles = None

        self._set_params(params)
        self._set_log_likes(log_likes)
        self._set_and_norm_log_weights(log_weights)

    @property
    def params(self):
        return self._params

    def _set_params(self, params):
        if not self._is_dict(params):
            raise TypeError('"params" must be dict of array-like objects.')
        self._param_names = tuple(params.keys())
        self._params = np.vstack(list(params.values())).T
        self._num_particles = self._params.shape[0]

    @property
    def param_dict(self):
        return dict(zip(self._param_names, self._params.T))

    @property
    def log_likes(self):
        return self._log_likes

    def _set_log_likes(self, log_likes):
        log_likes = np.array(log_likes).reshape(-1, 1)
        if log_likes.shape[0] != self._num_particles:
            raise ValueError('"log_likes.shape[0]" must match param arrays')
        self._log_likes = log_likes

    @property
    def log_weights(self):
        return self._log_weights

    @property
    def weights(self):
        return self._weights

    def _set_and_norm_log_weights(self, log_weights):
        log_weights = np.array(log_weights).reshape(-1, 1)
        if log_weights.shape[0] != self._num_particles:
            raise ValueError('"log_weights.shape[0]" must match param arrays')
        self._log_weights = self._normalize_log_weights(log_weights)
        self._weights = np.exp(self._log_weights)

    @property
    def param_names(self):
        return self._param_names

    @property
    def num_particles(self):
        return self._num_particles

    def _normalize_log_weights(self, log_weights):
        '''
        Normalizes log weights, and then transforms back into log space
        '''
        shifted_weights = np.exp(log_weights - max(log_weights))
        normalized_weights = shifted_weights / sum(shifted_weights)
        return np.log(normalized_weights)

    def copy(self):
        '''
        Returns a copy of the entire step class.
        '''
        return copy.deepcopy(self)

    def compute_ess(self):
        '''
        Computes the effective sample size (ess) of the step based on log weight
        '''
        return 1 / np.sum(self.weights ** 2)

    @package_for_user
    def compute_mean(self):
        '''
        Returns the estimated mean of each parameter.
        '''
        return np.sum(self.params * self.weights, axis=0)

    @package_for_user
    def compute_variance(self):
        '''
        Returns the estimated variance of each parameter. Uses weighted
        sample formula https://en.wikipedia.org/wiki/Sample_mean_and_covariance 
        '''
        means = self.compute_mean(package=False)
        norm = 1 - np.sum(self.weights ** 2)
        return np.sum(self.weights * (self.params - means) ** 2, axis=0) / norm

    @package_for_user
    def compute_std_dev(self):
        '''
        Returns the estimated standard deviation of each parameter. 
        '''
        var = self.compute_variance(package=False)
        return np.sqrt(var)

    def compute_covariance(self):
        '''
        Estimates the covariance matrix. Uses weighted sample formula
        https://en.wikipedia.org/wiki/Sample_mean_and_covariance 
        '''
        means = self.compute_mean(package=False)
        diff = self.params - means
        norm = 1 / (1 - np.sum(self.weights ** 2))
        cov = np.dot(diff.T, diff * self.weights) * norm

        if not self._is_positive_definite(cov):
            warnings.warn('Covariance matrix is not positive definite; setting '
                          'off-diagonal terms to zero.')
            cov= np.eye(cov.shape[0]) * np.diag(cov)

        return cov

    # MARKED FOR REFACTOR
    #@_mpi_decorator
    #def plot_marginal(self, key, save=False, show=True,
    #                  prefix='marginal_'):  # pragma no cover
    #    '''
    #    Plots a single marginal approximation for param given by <key>.
    #    '''
    #    try:
    #        plt
    #    except:
    #        import matplotlib.pyplot as plt
    #    fig = plt.figure()
    #    ax = fig.add_subplot(111)
    #    for p in self.particles:
    #        ax.plot([p.params[key], p.params[key]], [0.0, np.exp(p.log_weight)])
    #        ax.plot(p.params[key], np.exp(p.log_weight), 'o')
    #    if save:
    #        plt.savefig(prefix + key + '.png')
    #    if show:
    #        plt.show()
    #    plt.close(fig)
    #    return None

    #def plot_pairwise_weights(self, param_names=None, labels=None,
    #                          save=False, show=True, param_lims=None,
    #                          label_size=None, tick_size=None, nbins=None,
    #                          prefix='pairwise'):  # pragma no cover
    #    '''
    #    Plots pairwise distributions of all parameter combos. Color codes each
    #    by weight.
    #    '''
    #    try:
    #        plt
    #    except:
    #        import matplotlib.pyplot as plt
    #    # get particles
    #    particles = self.particles

    #    # set up label dictionary
    #    if param_names is None:
    #        param_names = particles[0].params.keys()
    #    if labels is None:
    #        labels = param_names
    #    label_dict = {key: lab for key, lab in zip(param_names, labels)}
    #    if param_lims is not None:
    #        lim_dict = {key: l for key, l in zip(param_names, param_lims)}
    #    if nbins is not None:
    #        bin_dict = {key: n for key, n in zip(param_names, nbins)}
    #    L = len(param_names)

    #    # setup figure
    #    fig = plt.figure(figsize=[10 * (L - 1) / 2, 10 * (L - 1) / 2])

    #    # create lower triangle to obtain param combos
    #    tril = np.tril(np.arange(L**2).reshape([L, L]), -1)
    #    ikeys = np.transpose(np.nonzero(tril)).tolist()

    #    # use lower triangle to id subplots
    #    tril = np.tril(np.arange((L - 1)**2).reshape([L - 1, L - 1]) + 1)
    #    iplts = [i for i in tril.flatten() if i > 0]

    #    norm_weights = self.normalize_step_weights()
    #    means = self.get_mean()
    #    for i in zip(iplts, ikeys):
    #        iplt = i[0]     # subplot index
    #        ikey1 = i[1][1]  # key index for xparam
    #        ikey2 = i[1][0]  # key index for yparam
    #        key1 = param_names[ikey1]
    #        key2 = param_names[ikey2]
    #        ax = {key1 + '+' + key2: fig.add_subplot(L - 1, L - 1, iplt)}
    #        # get list of all particle params for key1, key2 combinations
    #        pkey1 = []
    #        pkey2 = []
    #        for p in particles:
    #            pkey1.append(p.params[key1])
    #            pkey2.append(p.params[key2])
    #        # plot parameter combos with weight as color

    #        def rnd_to_sig(x):
    #            return round(x, -int(np.floor(np.log10(abs(x)))) + 1)
    #        sc = ax[key1 + '+' + key2].scatter(pkey1, pkey2, c=norm_weights, vmin=0.0,
    #                                           vmax=rnd_to_sig(max(norm_weights)))
    #        ax[key1 + '+' + key2].axvline(means[key1], color='C1', linestyle='--')
    #        ax[key1 + '+' + key2].axhline(means[key2], color='C1', linestyle='--')
    #        ax[key1 + '+' + key2].set_xlabel(label_dict[key1])
    #        ax[key1 + '+' + key2].set_ylabel(label_dict[key2])

    #        # if provided, set x y lims
    #        if param_lims is not None:
    #            ax[key1 + '+' + key2].set_xlim(lim_dict[key1])
    #            ax[key1 + '+' + key2].set_ylim(lim_dict[key2])
    #        # if provided set font sizes
    #        if tick_size is not None:
    #            ax[key1 + '+' + key2].tick_params(labelsize=tick_size)
    #        if label_size is not None:
    #            ax[key1 + '+' + key2].xaxis.label.set_size(label_size)
    #            ax[key1 + '+' + key2].yaxis.label.set_size(label_size)
    #        # if provided, set x ticks
    #        if nbins is not None:
    #            ax[key1 + '+' + key2].locator_params(axis='x', nbins=bin_dict[key1])
    #            ax[key1 + '+' + key2].locator_params(axis='y', nbins=bin_dict[key2])

    #    fig.tight_layout()

    #    # colorbar
    #    if L <= 2:
    #        cb = plt.colorbar(sc, ax=ax[key1 + '+' + key2])
    #    else:
    #        ax1_position = fig.axes[0].get_position()
    #        ax3_position = fig.axes[2].get_position()
    #        y0 = ax1_position.y0
    #        x0 = ax3_position.x0
    #        w = 0.02
    #        h = abs(ax1_position.y1 - ax1_position.y0)
    #        empty_ax = fig.add_axes([x0, y0, w, h])
    #        cb = plt.colorbar(sc, cax=empty_ax)
    #        if tick_size is not None:
    #            empty_ax.tick_params(labelsize=tick_size)

    #    cb.ax.get_yaxis().labelpad = 15
    #    cb.ax.set_ylabel('Normalized weights', rotation=270)

    #    plt.tight_layout()

    #    if save:
    #        plt.savefig(prefix + '.png')
    #    if show:
    #        plt.show()
    #    plt.close(fig)
    #    return None