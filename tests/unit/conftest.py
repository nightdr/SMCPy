import pytest

from smcpy.mcmc.translator_base import Translator


@pytest.fixture
def stub_comm(mocker):
    comm = mocker.Mock()
    comm.gather = lambda x, root: [x]
    return comm


@pytest.fixture
def stub_mcmc_kernel(mocker):
    stub_mcmc_kernel = mocker.Mock(Translator)
    mocker.patch.object(stub_mcmc_kernel, 'get_log_likelihood', create=True,
                        side_effect=[0.1, 0.1, 0.1, 0.2, 0.2])
    mocker.patch.object(stub_mcmc_kernel, 'get_log_prior', create=True,
                        side_effect=[0.2, 0.2, 0.2, 0.3, 0.3])
    return stub_mcmc_kernel