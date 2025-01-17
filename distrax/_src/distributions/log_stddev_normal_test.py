# Copyright 2021 DeepMind Technologies Limited. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for `log_stddev_normal.py`."""

from absl.testing import absltest
from absl.testing import parameterized

import chex
from distrax._src.distributions import log_stddev_normal as lsn
from distrax._src.distributions import normal
import jax
import jax.numpy as jnp
import mock
import numpy as np
from tensorflow_probability.substrates import jax as tfp


kl_module = tfp.distributions.kullback_leibler


class LogStddevNormalTest(parameterized.TestCase):

  @parameterized.parameters(
      (np.zeros((4,)), np.zeros((4,)), np.zeros((4,))),
      (np.zeros(()), np.zeros((4,)), np.zeros((4,))),
      (np.zeros((4,)), np.zeros(()), np.zeros((4,))),
  )
  def test_log_scale_property(self, mean, log_stddev, expected):
    dist = lsn.LogStddevNormal(mean, log_stddev)
    assert dist.log_scale.shape == expected.shape
    np.testing.assert_allclose(dist.log_scale, expected, atol=1e-4)

  @parameterized.parameters(
      (0.0, 1.0), (4.0, 10.0))
  def testSamplingScalar(self, mean, stddev):
    log_stddev = np.log(stddev)
    dist = lsn.LogStddevNormal(mean, log_stddev)

    num_samples = 1000000
    prng_key = jax.random.PRNGKey(1331)
    samples = dist.sample(seed=prng_key, sample_shape=num_samples)
    chex.assert_shape(samples, (num_samples,))
    np.testing.assert_allclose(jnp.mean(samples), mean, atol=4e-2)
    np.testing.assert_allclose(jnp.std(samples), stddev, atol=4e-2)

  @parameterized.parameters(
      ([3, 4], [1.5, 2.5]),
      ([0, 1, 0, 1, 10], [0.1, 0.5, 1.0, 5.0, 10.0]))
  def testSamplingVector(self, mean, stddev):
    mean = np.array(mean)
    log_stddev = np.log(stddev)
    assert mean.shape == log_stddev.shape
    dist = lsn.LogStddevNormal(mean, log_stddev)

    num_samples = 1000000
    prng_key = jax.random.PRNGKey(1331)
    samples = dist.sample(seed=prng_key, sample_shape=num_samples)
    chex.assert_shape(samples, (num_samples,) + mean.shape)
    np.testing.assert_allclose(jnp.mean(samples, axis=0), mean, atol=4e-2)
    np.testing.assert_allclose(jnp.std(samples, axis=0), stddev, atol=4e-2)

  def testSamplingBatched(self):
    means = np.array([[3.0, 4.0], [-5, 48.0], [58, 64.0]])
    stddevs = np.array([[1, 2], [2, 4], [4, 8]])
    log_stddevs = np.log(stddevs)
    dist = lsn.LogStddevNormal(means, log_stddevs)

    num_samples = 1000000
    prng_key = jax.random.PRNGKey(1331)
    samples = dist.sample(seed=prng_key, sample_shape=num_samples)
    # output shape is [num_samples] + means.shape
    chex.assert_shape(samples, (num_samples, 3, 2))
    np.testing.assert_allclose(jnp.mean(samples, axis=0), means, atol=4e-2)
    np.testing.assert_allclose(jnp.std(samples, axis=0), stddevs, atol=4e-2)

  def testSamplingBatchedCustomDim(self):
    means = np.array([[3.0, 4.0], [-5, 48.0], [58, 64.0]])
    stddevs = np.array([[1, 2], [2, 4], [4, 8]])
    log_stddevs = np.log(stddevs)
    dist = lsn.LogStddevNormal(means, log_stddevs)

    num_samples = 1000000
    prng_key = jax.random.PRNGKey(1331)
    samples = dist.sample(seed=prng_key, sample_shape=num_samples)
    chex.assert_shape(samples, (num_samples, 3, 2))
    np.testing.assert_allclose(jnp.mean(samples, axis=0), means, atol=4e-2)
    np.testing.assert_allclose(jnp.std(samples, axis=0), stddevs, atol=4e-2)

  @chex.all_variants
  @parameterized.named_parameters(
      ('float32', jnp.float32),
      ('float64', jnp.float64))
  def test_sample_dtype(self, dtype):
    dist = lsn.LogStddevNormal(
        loc=jnp.zeros((), dtype), log_scale=jnp.zeros((), dtype))
    samples = self.variant(dist.sample)(seed=jax.random.PRNGKey(0))
    self.assertEqual(samples.dtype, dist.dtype)
    chex.assert_type(samples, dtype)

  def testKLVersusNormal(self):
    loc, scale = jnp.array([2.0]), jnp.array([2.0])
    log_scale = jnp.log(scale)
    lsn_prior = lsn.LogStddevNormal(jnp.array([0.0]), jnp.array([0.0]))
    n_prior = normal.Normal(jnp.array([0.0]), jnp.array([1.0]))
    lsn_dist = lsn.LogStddevNormal(loc, log_scale)
    n_dist = normal.Normal(loc, scale)

    kl1 = tfp.distributions.kl_divergence(lsn_dist, lsn_prior)
    kl2 = tfp.distributions.kl_divergence(n_dist, lsn_prior)
    kl3 = tfp.distributions.kl_divergence(n_dist, n_prior)
    np.testing.assert_allclose(kl2, kl1)
    np.testing.assert_allclose(kl3, kl2)
    np.testing.assert_allclose(kl1, kl3)

  # pylint:disable=protected-access
  def testCustomKLRegistered(self):
    # Check that our custom KL is registered inside the TFP dispatch table.
    dist_pair = (lsn.LogStddevNormal, lsn.LogStddevNormal)
    self.assertEqual(kl_module._DIVERGENCES[dist_pair],
                     lsn._kl_logstddevnormal_logstddevnormal)

  @mock.patch.dict(
      kl_module._DIVERGENCES,
      {(lsn.LogStddevNormal,
        lsn.LogStddevNormal): lambda *args, **kwargs: 42})
  def testCallingCustomKL(self):
    # Check that the dispatch of tfp.kl_divergence actually goes to the
    # table we checked for above.
    dist_a = lsn.LogStddevNormal(jnp.array([0.0]), jnp.array([0.0]))
    dist_b = lsn.LogStddevNormal(jnp.array([0.0]), jnp.array([0.0]))
    self.assertEqual(tfp.distributions.kl_divergence(dist_a, dist_b), 42)
  # pylint:enable=protected-access

  def test_jitable(self):
    @jax.jit
    def jitted_function(event, dist):
      return dist.log_prob(event)

    dist = lsn.LogStddevNormal(np.array([0.0]), np.array([0.0]))
    event = dist.sample(seed=jax.random.PRNGKey(0))
    jitted_function(event, dist)

if __name__ == '__main__':
  absltest.main()
