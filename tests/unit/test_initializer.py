import numpy as np
import pandas
import pytest

from collections import namedtuple

from smcpy.smc.initializer import Initializer
from smcpy.mcmc.translator_base import Translator


class StubSMCStep:

    def __init__(self):
        pass

    def set_particles(self, particles):
        self.particles = particles


@pytest.fixture
def stub_comm(mocker):
    comm = mocker.Mock()
    return comm


@pytest.fixture
def stub_mcmc_kernel(mocker):
    stub_mcmc_kernel = mocker.Mock(Translator)
    mocker.patch.object(stub_mcmc_kernel, 'sample_from_prior', create=True,
                        return_value={'a': [1, 1, 1, 2, 2]})
    mocker.patch.object(stub_mcmc_kernel, 'get_log_likelihood', create=True,
                        side_effect=[0.1, 0.1, 0.1, 0.2, 0.2])
    mocker.patch.object(stub_mcmc_kernel, 'get_log_prior', create=True,
                        side_effect=[0.2, 0.2, 0.2, 0.3, 0.3])
    return stub_mcmc_kernel


@pytest.fixture
def initializer(stub_mcmc_kernel, stub_comm, mocker):
    particle_stub = namedtuple('Particle', ['params', 'log_weight', 'log_like'])
    mocker.patch('smcpy.smc.initializer.Particle', new=particle_stub)
    mocker.patch('smcpy.smc.initializer.SMCStep', new=StubSMCStep)
    initializer = Initializer(stub_mcmc_kernel, phi_init=2, mpi_comm=stub_comm)
    return initializer


@pytest.mark.parametrize('rank,expected', [(0, 4), (1, 3), (2, 3)])
def test_get_num_particles_in_partition(stub_comm, stub_mcmc_kernel, rank,
                                         expected, mocker):
    mocker.patch.object(stub_comm, 'Get_size', return_value=3)
    mocker.patch.object(stub_comm, 'Get_rank', return_value=rank)
    initializer = Initializer(stub_mcmc_kernel, None, mpi_comm=stub_comm)
    assert initializer.get_num_particles_in_partition(10, rank) == expected


def test_mcmc_kernel_not_translator_instance():
    with pytest.raises(TypeError):
        initializer = Initializer(None, None)


def test_initialize_particles_from_prior(initializer, mocker):
    mocker.patch.object(initializer, 'get_num_particles_in_partition',
                        new=lambda x, y: x)
    smc_step = initializer.initialize_particles_from_prior(5)
    particles = smc_step.particles

    expected_a_vals = [1, 1, 1, 2, 2]
    expected_log_like = [0.1, 0.1, 0.1, 0.2, 0.2]
    expected_log_weight = [0.2] * 3 + [0.4] * 2

    np.testing.assert_array_almost_equal([p.params['a'] for p in particles],
                                         expected_a_vals)
    np.testing.assert_array_almost_equal([p.log_like for p in particles],
                                         expected_log_like)
    np.testing.assert_array_almost_equal([p.log_weight for p in particles],
                                         expected_log_weight)


@pytest.mark.parametrize('rank,expected_params,dataframe',
                         [(0, {'a': [3, 3, 3, 4, 4], 'b': [1, 1, 1, 2, 2]}, 0),
                          (1, {'a': [1, 1, 1, 2, 2], 'b': [2, 2, 2, 5, 5]}, 0),
                          (1, {'a': [1, 1, 1, 2, 2], 'b': [2, 2, 2, 5, 5]}, 1),
                          (2, {'a': [3, 4, 5, 5], 'b': [1, 2, 3, 4]}, 0)])
def test_initialize_particles_from_samples(rank, expected_params, initializer,
                                           dataframe):
    samples = {'a': np.array([3, 3, 3, 4, 4, 1, 1, 1, 2, 2, 3, 4, 5, 5]),
               'b': np.array([1, 1, 1, 2, 2, 2, 2, 2, 5, 5, 1, 2, 3, 4])}

    if dataframe:
        samples = pandas.DataFrame(samples)

    proposal_pdensity = np.array(samples['a']) * 0.1

    initializer._size = 3
    initializer._rank = rank

    smc_step = initializer.initialize_particles_from_samples(samples,
                                                             proposal_pdensity)
    particles = smc_step.particles

    expected_length = len(expected_params['a'])
    expected_log_like = [0.1, 0.1, 0.1, 0.2, 0.2][:expected_length]
    expected_log_prior = np.array([0.4] * 3 + [0.7] * 2)[:expected_length]
    expected_log_prop = np.log(np.array(expected_params['a']) * 0.1)
    expected_log_weight = expected_log_prior - expected_log_prop

    np.testing.assert_array_almost_equal([p.params['a'] for p in particles],
                                          expected_params['a'])
    np.testing.assert_array_almost_equal([p.params['b'] for p in particles],
                                          expected_params['b'])
    np.testing.assert_array_almost_equal([p.log_like for p in particles],
                                         expected_log_like)
    np.testing.assert_array_almost_equal([p.log_weight for p in particles],
                                         expected_log_weight)