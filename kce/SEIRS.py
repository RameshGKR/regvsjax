import jax
import jax.numpy as jnp
import numpy as np
import pandas as pd


class Model:
    def __init__(self):
        # contact matrix
        df = pd.read_csv("data/close+15_old.csv")
        self.contact = jnp.asarray(df.values)
        # mortality rates
        df = pd.read_csv("data/rateMor_eurostat_2021.csv")
        df.drop(df.tail(1).index, inplace=True)  # FIXME
        self.dailyMort = jnp.asarray(df["Value"].values) / 365
        # initial population
        df = pd.read_csv("data/refPop_eurostat_2021.csv")
        df.drop(df.tail(1).index, inplace=True)  # FIXME
        self.initPop = jnp.asarray(df["Population"].values,
                                   dtype=float)
        self.totPop = self.initPop.sum().astype(float)
        # TODO: vaccination efficacy
        # other parameters
        self.q = 1.8 / 15.2153
        self.sigma = 0.5
        self.gamma = 0.5
        self.omegaImm = 0.33 / 365
        self.omegaVacc = 0.33 / 365
        self.seedInf = 200
        self.seedAges = jnp.asarray(range(5, 51))
        self.delta = 0.7
        # other constants
        self.peak = 1  # day of the year (out of 365)
        self.birthday = 248  # 8 * 31 ~ End of August
        self.startDate = 279  # 9 * 31 ~ End of September
        self.seedDate = 341  # 11 * 31 ~ End of November
        self.vaccDate = 289  # 9 * 31 + 10 ~ October 10

    def init(self):
        S = self.initPop
        E = jnp.zeros(S.size)
        Inf = jnp.zeros(S.size)
        R = jnp.zeros(S.size)
        V = jnp.zeros(S.size)
        return (S, E, Inf, R, V, self.startDate)

    # We simulate one step of (forward) Newton integration
    # with h = 1 (day). For efficiency, this just calls a
    # function and passes the right arguments/attributes. Then,
    # that function can be JIT compiled
    def step(self, S, E, Inf, R, V, day):
        return _step(S, E, Inf, R, V, day,
                     peak=self.peak,
                     contact=self.contact,
                     q=self.q,
                     sigma=self.sigma,
                     gamma=self.gamma,
                     omegaImm=self.omegaImm,
                     omegaVacc=self.omegaVacc,
                     dailyMort=self.dailyMort)

    def seedInfs(self, S, E, Inf, R, V, day):
        newS = S.at[self.seedAges].add(-self.seedInf)
        newE = E.at[self.seedAges].add(self.seedInf)
        return (newS, newE, Inf, R, V, day)

    def vaccinate(self, S, E, Inf, R, V, day):
        return (S, E, Inf, R, V, day)

    def age(self, S, E, Inf, R, V, day):
        newS = jnp.roll(S, 1).at[0].set(0)
        newE = jnp.roll(E, 1).at[0].set(0)
        newInf = jnp.roll(Inf, 1).at[0].set(0)
        newR = jnp.roll(R, 1).at[0].set(0)
        newV = jnp.roll(V, 1).at[0].set(0)
        # reincarnate dead people
        curPop = jnp.asarray([newS, newE, newInf, newR]).sum()
        newS = newS.at[0].set(self.totPop - curPop)
        return (newS, newE, newInf, newR, newV, day)


@jax.jit
def _step(S, E, Inf, R, V, day,
          peak, contact, q, sigma, gamma,
          omegaImm, omegaVacc, dailyMort):
    z = 1 + jnp.sin(2 * np.pi * (day - peak) / 365)
    beta = contact * q
    force = z * jnp.dot(beta, Inf)

    # daily transitions
    S2E = S * force  # element-wise product
    E2I = E * sigma
    I2R = Inf * gamma
    R2S = R * omegaImm
    V2S = V * omegaVacc

    # daily mortality = element-wise product with mortality
    # rates
    S2D = S * dailyMort
    E2D = E * dailyMort
    I2D = Inf * dailyMort
    R2D = R * dailyMort
    V2D = R * dailyMort

    # new values for all components
    newS = S - S2E + R2S + V2S - S2D
    newE = E + S2E - E2I - E2D
    newInf = Inf + E2I - I2R - I2D
    newR = R + I2R - R2S - R2D
    newV = V - V2S - V2D
    return (newS, newE, newInf, newR, newV, day + 1)
