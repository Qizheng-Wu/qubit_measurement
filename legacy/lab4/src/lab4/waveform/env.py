"""
Envelope class for generating microwave sequences.


This is from the pyle package of John Martinis group.
"""
# Control envelopes in time domain and frequency domain
#
# For a pair of functions g(t) <-> h(f) we use the following
# convention for the Fourier Transform:
#
#          / +inf
#         |
# h(f) =  | g(t) * exp(-2j*pi*f*t) dt
#         |
#        / -inf
#
#          / +inf
#         |
# g(t) =  | h(f) * exp(2j*pi*f*t) df
#         |
#        / -inf
#
# Note that we are working with frequency in GHz, rather than
# angular frequency.  Also note that the sign convention is opposite
# to what is normally taken in physics.  But this is the convention
# used here and in the DAC deconvolution code, so you should use it.
import cmath
import logging
import math
from functools import wraps

import matplotlib.pyplot as plt
import numpy as np
from scipy.special import erf

logger = logging.getLogger(__name__)

USE_NUMBA = True
try:
    from numba import njit
except ImportError:
    USE_NUMBA = False
    logger.warning("Numba not installed, falling back to pure python")

# If using numba causes problems, you can disable it here
# USE_NUMBA = False


class Envelope(object):
    """Represents a control envelope as a function of time or frequency.

    Envelopes can be added to each other or multiplied by constant values.
    Multiplication of two envelopes and addition of a constant value (other
    than zero) are not equivalent in time and fourier domains, so these
    operations are not supported.

    Envelopes keep track of their start and end time, and when added
    together the new envelope will use the earliest start and latest end,
    to cover the entire range of its constituent parts.

    Envelopes can be evaluated as functions of time or frequency using the
    fourier flag.  By default, they are evaluated as a function of time.
    """
    def __init__(self, timeFunc, freqFunc, start=None, end=None):
        self.timeFunc = timeFunc
        self.freqFunc = freqFunc
        self.start = start
        self.end = end
        self.terms = [(1, self)]

    def __call__(self, x, fourier=False):
        if fourier:
            return self._eval_freq_func(x)
        else:
            return self._eval_time_func(x)
        
    def _eval_time_func(self, x):
        accumulator = np.zeros_like(x, dtype=complex)
        for v, e in self.terms:
            s = get_slice(x, e.start, e.end)
            accumulator[s] += v * e.timeFunc(x[s])
        return accumulator
   
    def _eval_freq_func(self, x):
        accumulator = np.zeros_like(x, dtype=complex)
        for v, e in self.terms:
            accumulator += v * e.freqFunc(x)
        return accumulator

    def __add__(self, other):
        if isinstance(other, Envelope):
            start, end = timeRange((self, other))
            def timeFunc(t):
                return self.timeFunc(t) + other.timeFunc(t)
            def freqFunc(f):
                return self.freqFunc(f) + other.freqFunc(f)
            new_env = Envelope(timeFunc, freqFunc, start=start, end=end)
            new_env.terms = self.terms + other.terms
            return new_env
        else:
            # if we try to add envelopes with the built in sum() function,
            # the first envelope is added to 0 before adding the rest.  To support
            # this, we add a special case here since adding 0 in time or fourier
            # is equivalent
            if other == 0:
                return self
            raise Exception("Cannot add a constant to hybrid time/fourier envelopes")
    __radd__ = __add__

    def __sub__(self, other):
        if isinstance(other, Envelope):
            start, end = timeRange((self, other))
            def timeFunc(t):
                return self.timeFunc(t) - other.timeFunc(t)
            def freqFunc(f):
                return self.freqFunc(f) - other.freqFunc(f)
            new_env = Envelope(timeFunc, freqFunc, start=start, end=end)
            new_env.terms = self.terms + [(-v, e) for v, e in other.terms]
            return new_env
        else:
            # if we try to add envelopes with the built in sum() function,
            # the first envelope is added to 0 before adding the rest.  To support
            # this, we add a special case here since adding 0 in time or fourier
            # is equivalent
            if other == 0:
                return -self
            raise Exception("Cannot subtract a constant from hybrid time/fourier envelopes")

    def __rsub__(self, other):
        if isinstance(other, Envelope):
            start, end = timeRange((self, other))
            def timeFunc(t):
                return other.timeFunc(t) - self.timeFunc(t)
            def freqFunc(f):
                return other.freqFunc(f) - self.freqFunc(f)
            new_env = Envelope(timeFunc, freqFunc, start=start, end=end)
            new_env.terms = [(-v, e) for v, e in self.terms] + other.terms
            return new_env
        else:
            # if we try to add envelopes with the built in sum() function,
            # the first envelope is added to 0 before adding the rest.  To support
            # this, we add a special case here since adding 0 in time or fourier
            # is equivalent
            if other == 0:
                return self
            raise Exception("Cannot subtract a constant from hybrid time/fourier envelopes")

    def __mul__(self, other):
        if isinstance(other, Envelope):
            raise Exception("Hybrid time/fourier envelopes can only be multiplied by constants")
        else:
            def timeFunc(t):
                return self.timeFunc(t) * other
            def freqFunc(f):
                return self.freqFunc(f) * other
            new_env = Envelope(timeFunc, freqFunc, start=self.start, end=self.end)
            new_env.terms = [(v*other, e) for v, e in self.terms]
            return new_env
    __rmul__ = __mul__

    def __div__(self, other):
        if isinstance(other, Envelope):
            raise Exception("Hybrid time/fourier envelopes can only be divided by constants")
        else:
            def timeFunc(t):
                return self.timeFunc(t) / other
            def freqFunc(f):
                return self.freqFunc(f) / other
            new_env = Envelope(timeFunc, freqFunc, start=self.start, end=self.end)
            new_env.terms = [(v/other, e) for v, e in self.terms]
            return new_env

    
    __truediv__ = __div__

    def __rdiv__(self, other):
        if isinstance(other, Envelope):
            raise Exception("Hybrid time/fourier envelopes can only be divided by constants")
        else:
            def timeFunc(t):
                return other / self.timeFunc(t)
            def freqFunc(f):
                return other / self.freqFunc(f)
            return Envelope(timeFunc, freqFunc, start=self.start, end=self.end)

    __rtruediv__ = __rdiv__

    def __neg__(self):
        return -1 * self

    def __pos__(self):
        return self


_zero = lambda x: np.zeros_like(x,dtype=float)


# empty envelope
NOTHING = Envelope(_zero, _zero, start=None, end=None)
NOTHING.terms = []

def ezpulse(
    t0_ns: float,
    amp: float,
    len_ns: float,
    freq_GHz: float,
    width_ns: float = 5,
    phase: float = 0,
    zero_phase_at_t0: bool = True,  # Set phase at t0 to 0.
):
    if zero_phase_at_t0:
        phase += 2 * np.pi * freq_GHz * t0_ns  # the mix phase at t0 is -2*np.pi*freq*t0

    if width_ns == 0:
        shape = rect(t0_s=t0_ns*1e-9, len_s=len_ns*1e-9, amp=amp, phase=phase)
    else:
        shape = flattop(t0_s=t0_ns*1e-9, len_s=len_ns*1e-9, amp=amp, w_s=width_ns*1e-9, phase=phase)
        
    return mix(shape, freq_GHz*1e9)
def mix_on_top(
    t0_ns: float,
    zpa: float,
    plateau_ns: float,
    width_ns: float,
    amp: float = 0,
    freq_GHz: float = 0.1,
    phase: float = 0,
    zero_phase_at_t0: bool = True,
):
    """
    ----t0--------------------t0+len---
    
    |--width--|---plateau---|--width--|
    """
    if zero_phase_at_t0:
        phase += 2 * np.pi * freq_GHz * t0_ns  # the mix phase at t0 is -2*np.pi*freq*t0

    if width_ns == 0:
        shape = rect(t0_s=t0_ns*1e-9, len_s=plateau_ns*1e-9, amp=zpa)
    else:
        shape = flattop(t0_s=t0_ns*1e-9, len_s=(plateau_ns + width_ns)*1e-9, amp=zpa, w_s=width_ns*1e-9/2)
        
    if amp != 0:
        shape += mix_cosine(rect(t0_s=(t0_ns+width_ns/2)*1e-9, len_s=plateau_ns*1e-9, amp=amp), freq_GHz*1e9, phase=phase)
    return shape

def gaussian(t0_s, w_s, amp=1.0, phase=0.0, df_Hz=0.0):
    """A gaussian pulse with specified center and full-width at half max."""
    t0_ns = t0_s * 1e9
    w_ns = w_s * 1e9
    df_GHz = df_Hz * 1e-9
    sigma = w_ns / np.sqrt(8*np.log(2)) # convert fwhm to std. deviation
    def timeFunc(t):
        return amp * np.exp(-(t-t0_ns)**2/(2*sigma**2) - 2j*np.pi*df_GHz*(t-t0_ns) + 1j*phase)

    sigmaf = 1 / (2*np.pi*sigma) # width in frequency space
    ampf = amp * np.sqrt(2*np.pi*sigma**2) # amp in frequency space
    def freqFunc(f):
        return  ampf * np.exp(-(f+df_GHz)**2/(2*sigmaf**2) - 2j*np.pi*f*t0_ns + 1j*phase)
        # return ampf * np.exp(-(f+df)**2/(2*sigmaf**2) - 2j*np.pi*f*t0 + 1j*phase)

    return Envelope(timeFunc, freqFunc, start=t0_ns-w_ns, end=t0_ns+w_ns)

def halfgaussian(t0_s, w_s, amp=1.0):
    """A truncated gaussian pulse with specified center and full-width at half max."""
    t0_ns = t0_s * 1e9
    w_ns = w_s * 1e9
    sigma = w_ns / np.sqrt(8*np.log(2)) # convert fwhm to std. deviation
    def timeFunc(t):
        return  (t <= t0_ns)*amp * np.exp(-(t-t0_ns)**2/(2*sigma**2))
    sigmaf = 1 / (2*np.pi*sigma) # width in frequency space
    ampf = amp * np.sqrt(2*np.pi*sigma**2) # amp in frequency space

    te=np.pi*sigma
    def freqFunc(f):
        z = f==0
        z2=(np.abs(f)*sigma<=5.5)
        return 0.5*((1-z)*ampf *1j* np.exp(-f**2/(2*sigmaf**2) - 2j*np.pi*f*t0_ns)*(1+erf(1j*np.sqrt(2)*np.pi*(f*sigma)*z2)+(z2-1)))
    return Envelope(timeFunc, freqFunc, start=t0_ns-w_ns, end=t0_ns)

def triangle(t0_s, len_s, amp, fall=True,ini_amp = 0):
    """A triangular pulse, either rising or falling."""
    if not fall:
        return triangle(t0_ns+len_ns, -len_ns, amp, fall=True, ini_amp=ini_amp)
    t0_ns = t0_s * 1e9
    len_ns = len_s * 1e9

    tmin_ns = min(t0_ns, t0_ns+len_ns)
    tmax_ns = max(t0_ns, t0_ns+len_ns)
    if len_ns == 0 or amp == 0:
        return Envelope(_zero, _zero, start=tmin_ns, end=tmax_ns)

    def timeFunc(t):
        return amp * (t >= tmin_ns) * (t < tmax_ns) * (1 - (t-t0_ns)/len_ns) + ini_amp
    def freqFunc(f):
        # this is tricky because the fourier transform has a 1/f term, which blows up for f=0
        # the z array allows us to separate the zero-frequency part from the rest
        z = f == 0
        f = 2j*np.pi*(f + z)
        offset_fft = ini_amp * abs(len_ns) * np.sinc(len_ns*f) * np.exp(-2j*np.pi*f*0.5*(tmin_ns+tmax_ns))
        if len_ns < 0:
            return -amp * ((1-z)*np.exp(-f*t0_ns)*(1.0/f - (1-np.exp(-f*len_ns))/(f**2*len_ns)) + z*len_ns/2.0) + offset_fft
        else:
            return amp * ((1-z)*np.exp(-f*t0_ns)*(1.0/f - (1-np.exp(-f*len_ns))/(f**2*len_ns)) + z*len_ns/2.0) + offset_fft

    return Envelope(timeFunc, freqFunc, start=tmin_ns, end=tmax_ns)


def rect(t0_s, len_s, amp, overshoot=0.0, overshoot_w_ns=1.0):
    """A rectangular pulse with sharp turn on and turn off.

    Note that the overshoot_w_ns parameter, which defines the FWHM of the gaussian overshoot peaks
    is only used when evaluating the envelope in the time domain.  In the fourier domain, as is
    used in the dataking code which uploads sequences to the boards, the overshoots are delta
    functions.
    """
    t0_ns = t0_s * 1e9
    len_ns = len_s * 1e9
    tmin_ns = min(t0_ns, t0_ns+len_ns)
    tmax_ns = max(t0_ns, t0_ns+len_ns)
    tmid_ns = (tmin_ns + tmax_ns) / 2.0
    overshoot *= np.sign(amp) # overshoot will be zero if amp is zero

    # to add overshoots in time, we create an envelope with two gaussians
    if overshoot:
        o_w_ns = overshoot_w_ns
        o_amp = 2*np.sqrt(np.log(2)/np.pi) / o_w_ns # total area == 1
        o_env = gaussian(tmin_ns*1e-9, o_w_ns*1e-9, o_amp) + gaussian(tmax_ns*1e-9, o_w_ns*1e-9, o_amp)
    else:
        o_env = NOTHING
    def timeFunc(t):
        return (amp * (t >= tmin_ns) * (t < tmax_ns) +
                overshoot * o_env(t))

    # to add overshoots in frequency, use delta funcs (smoothed by filters)
    def freqFunc(f):
        return (amp * abs(len_ns) * np.sinc(len_ns*f) * np.exp(-2j*np.pi*f*tmid_ns) +
                overshoot * (np.exp(-2j*np.pi*f*tmin_ns) + np.exp(-2j*np.pi*f*tmax_ns)))

    return Envelope(timeFunc, freqFunc, start=tmin_ns, end=tmax_ns)

def flattop(t0_s, len_s, amp, w_s=5e-9, phase=0., overshoot=0.0, overshoot_w_ns=1.0):
    """A rectangular pulse convolved with a gaussian to have smooth rise and fall."""
    t0_ns = t0_s * 1e9
    len_ns = len_s * 1e9
    w_ns = w_s * 1e9
    tmin_ns = min(t0_ns, t0_ns+len_ns)
    tmax_ns = max(t0_ns, t0_ns+len_ns)

    overshoot *= np.sign(amp) # overshoot will be zero if amp is zero

    # to add overshoots in time, we create an envelope with two gaussians
    a = 2*np.sqrt(np.log(2)) / w_ns
    if overshoot:
        o_w_ns = overshoot_w_ns
        o_amp = 2*np.sqrt(np.log(2)/np.pi) / o_w_ns # total area == 1
        o_env = gaussian(tmin_ns*1e-9, o_w_ns*1e-9, o_amp) + gaussian(tmax_ns*1e-9, o_w_ns*1e-9, o_amp)
    else:
        o_env = NOTHING

    amp = amp * np.exp(1j*phase)  # BUG: amp *= np.exp(1j*phase) triggers bug in 2023.7.19. Too late?

    def timeFunc(t):
        return (amp * (erf(a*(tmax_ns - t)) - erf(a*(tmin_ns - t)))/2.0 +
                overshoot * o_env(t))

    # to add overshoots in frequency, use delta funcs (smoothed by filters)
    rect_env = rect(t0_ns*1e-9, len_ns*1e-9, 1.0)
    kernel = gaussian(0*1e-9, w_ns*1e-9, 2*np.sqrt(np.log(2)/np.pi) / w_ns) # area = 1
    def freqFunc(f):
        return (amp * rect_env(f, fourier=True) * kernel(f, fourier=True) + # convolve with gaussian kernel
                overshoot * (np.exp(-2j*np.pi*f*tmin_ns) + np.exp(-2j*np.pi*f*tmax_ns)))

    return Envelope(timeFunc, freqFunc, start=tmin_ns-2*w_ns, end=tmax_ns+2*w_ns)


def trapezoid(t0_s, rise_s, hold_s, fall_s, amp):
    """Create a trapezoidal pulse, built up from triangles and rectangles."""
    return (triangle(t0_s, rise_s, amp, fall=False) +
            rect(t0_s+rise_s, hold_s, amp) +
            triangle(t0_s+rise_s+hold_s, fall_s, amp))

def pwlin(t0_s, tbin_s, bin_amps,periodicTimeSteps = True):
    """Create a piecewise-linear pulse, built up from rectangles."""
    if periodicTimeSteps:
        pulse = rect(t0_s,tbin_s,bin_amps[0])
        for i, bin_amp in enumerate(bin_amps[1:]):
            t0_s+=tbin_s
            pulse += rect(t0_s,tbin_s, bin_amp)
    else:
        pulse = rect(t0_s,tbin_s[0],bin_amps[0])
        t0_s += tbin_s[0]
        for t_i, bin_amp in zip(tbin_s[1:],bin_amps[1:]):
            pulse += rect(t0_s,t_i, bin_amp)
            t0_s+=t_i

    return pulse

def parabola(t0_s, len_s, amp):
    """A parabola pulse"""
    t0_ns = t0_s * 1e9
    len_ns = len_s * 1e9
    tmin_ns = min(t0_ns, t0_ns+len_ns)
    tmax_ns = max(t0_ns, t0_ns+len_ns)
    if len_ns == 0 or amp == 0:
        return Envelope(_zero, _zero, start=tmin_ns, end=tmax_ns)

    def timeFunc(t):
        return amp * (t >= tmin_ns) * (t <= tmax_ns) * (1-(t-t0_ns-(len_ns/2))**2/(len_ns/2)**2)

    def freqFunc(f):
        nu = np.pi * f
        nu0 = nu == 0
        nu += nu0
        return 2.0/3.0*amp*len_ns*nu0 + \
            (1-nu0)* np.exp(-2j*nu*(t0_ns+0.5*len_ns)) * 2 * amp/len_ns/nu**2 * \
            (np.sin(len_ns * nu)/(len_ns*nu)-np.cos(len_ns*nu))

    return Envelope(timeFunc, freqFunc, start=tmin_ns, end=tmax_ns)

def cosine(t0_s, len_s, amp, phase=0):
    """A cosine-shape pulse.
    """
    t0_ns = t0_s * 1e9
    len_ns = len_s * 1e9
    if len_ns == 0.0:
        len_ns = 1e-6
    def timeFunc(t):
        return amp*(np.cos(2*np.pi*(t-t0_ns)/len_ns)+1.0)/2.0*np.exp(1j*phase)*(np.sign(t-t0_ns+len_ns/2.0)+1)/2.0*(np.sign(t0_ns+len_ns/2.0-t)+1)/2.0
    def freqFunc(f):
        return amp/2.0*(len_ns/2.0*np.sinc(1.0-len_ns*f)+len_ns/2.0*np.sinc(-1.0-len_ns*f)+len_ns*np.sinc(len_ns*f))* np.exp(-2j*np.pi*f*t0_ns+ 1j*phase)

    return Envelope(timeFunc, freqFunc, start=-len_ns/2.0+t0_ns,end=len_ns/2.0+t0_ns)

def DC(amp,total_sequence_length=None):
    """DC offset in Z pulse. Added by Youpeng Zhong, Dec 18, 2020."""
    def timeFunc(t):
        return amp
    def freqFunc(f): # need to know the total sequence length!!!
        return 2.0*amp*total_sequence_length* (f > -1e-6) * (f < 1e-6)

    return Envelope(timeFunc, freqFunc, start=None,end=None)

if USE_NUMBA:
    @njit
    def _mix_core(y, t, df):
        assert len(y) == len(t)
        if len(t) == 0:
            return y
        p0 = -math.tau * df * t[0]
        c0 = cmath.rect(1.0, p0)
        if len(t) == 1:
            y[0] *= c0
            return y
        dp = -math.tau * df * (t[1] - t[0])
        dc = cmath.rect(1.0, dp)
        for i in range(len(y)):
            y[i] *= c0
            c0 *= dc
        return y
    
    @njit
    def _mix_cosine_core(y, t, df):
        assert len(y) == len(t)
        if len(t) == 0:
            return y
        p0 = -math.tau * df * t[0]
        c0 = cmath.rect(1.0, p0)
        if len(t) == 1:
            y[0] *= c0.real
            return y
        dp = -math.tau * df * (t[1] - t[0])
        dc = cmath.rect(1.0, dp)
        for i in range(len(y)):
            y[i] *= c0.real
            c0 *= dc
        return y


def return_nothing_if_get_nothing(f):
    """A patch for envelop operations, not work for Envelop.__sub__ and etc."""
    @wraps(f)
    def wrapped_f(env, *args, **kwargs):
        if env is NOTHING:
            return NOTHING
        else:
            return f(env, *args, **kwargs)
    return wrapped_f


@return_nothing_if_get_nothing
def mix(env, df_Hz=0.0):
    """Apply sideband mixing at difference frequency df."""
    df_GHz = df_Hz * 1e-9
    # if abs(df)>0.3:
    #     raise Exception('the sideband frequency %f GHz is beyond the bandwidth of the custom boards!'%df)
    if USE_NUMBA:
        def timeFunc(t):
            return _mix_core(env(t), t, df_GHz)
    else:
        def timeFunc(t):
            return env(t) * np.exp(-2j*np.pi*df_GHz*t)
    def freqFunc(f):
        return env(f + df_GHz, fourier=True)
    return Envelope(timeFunc, freqFunc, start=env.start, end=env.end)

# NOTE: phase added by Jiawei Qiu and not considering freqFunc.
@return_nothing_if_get_nothing
def mix_cosine(env, df_Hz=0.0, phase=0):
    """Apply sideband mixing at difference frequency df."""
    df_GHz = df_Hz * 1e-9
    # if abs(df)>0.3:
    #     raise Exception('the sideband frequency %f GHz is beyond the bandwidth of the custom boards!'%df)
    if USE_NUMBA:
        def timeFunc(t):
            return _mix_cosine_core(env(t), t, df_GHz)
    else:
        def timeFunc(t):
            return env(t) * np.cos(2*np.pi*df_GHz*t + phase)
    def freqFunc(f):
        return 0.5*env(f + df_GHz, fourier=True)+0.5*env(f - df_GHz, fourier=True)
    return Envelope(timeFunc, freqFunc, start=env.start, end=env.end)

@return_nothing_if_get_nothing
def deriv(env, dt_s=0.1):
    """Get the time derivative of a given envelope."""
    dt_ns = dt_s * 1e9
    def timeFunc(t):
        return (env(t+dt_ns) - env(t-dt_ns)) / (2*dt_ns)
    def freqFunc(f):
        return 2j*np.pi*f * env(f, fourier=True)
    return Envelope(timeFunc, freqFunc, start=env.start, end=env.end)

@return_nothing_if_get_nothing
def shift(env, dt_s):
    """Shift an envelope in time."""
    dt_ns = dt_s * 1e9
    def timeFunc(t):
        return env(t - dt_ns)
    def freqFunc(f):
        return env(f, fourier=True) * np.exp(-2j*np.pi*f*dt_ns)
    new_start = env.start + dt_ns if env.start is not None else None
    new_end = env.end + dt_ns if env.end is not None else None
    return Envelope(timeFunc, freqFunc, start=new_start, end=new_end)


def mask(t, tmin, tmax):
    """Return 1 if tmin < t < tmax, 0 otherwise."""
    return (np.sign(tmax-t) + np.sign(t-tmin)) / 2.

def half_cosine(t0_s, plateau_s, amp, width_s):
    """Returns envelope with half-cosine edge."""
    t0_ns = t0_s * 1e9
    width_ns = width_s * 1e9
    plateau_ns = plateau_s * 1e9
    if width_ns == 0:
        t1 = t0_ns + plateau_ns
        if plateau_ns == 0:
            def time_func(t):
                return np.zeros_like(t)
        else:
            def time_func(t):
                return amp*(t0_ns <= t)*(t <= t1)
    else:
        hw = width_ns / 2.  # Half width
        t1 = t0_ns + width_ns + plateau_ns
        def time_func(t):
            t = t-t0_ns
            pt_rise = np.sin(t/hw*np.pi/2.) * mask(t, 0., hw)
            pt_fall = np.sin((t-hw-plateau_ns)/hw*np.pi/2. + np.pi/2.) * mask(t, hw+plateau_ns, 2.*hw+plateau_ns)
            pt_plat = 1. * mask(t, hw, hw+plateau_ns)
            return amp*(pt_rise + pt_plat + pt_fall)

    def freq_func(f):
        # Pad time series for dense frequency points.
        pad_len = 200000
        vt = np.arange(t0_ns-pad_len, t1+pad_len)
        # Round size padded time series to power of 2, for sake of faster FFT.
        # BUG: np.ceil(1.000000000000000000000014) = 2. See PEP238.
        n_pts = 2**int(np.ceil(np.log2(vt.size)))
        margin = (n_pts-np.ceil(t1-t0_ns)) / 2.
        pre_pad_len = int(np.ceil(margin))
        post_pad_len = int(np.floor(margin))
        vt = np.arange(t0_ns-pre_pad_len-2, t1+post_pad_len+2)[:n_pts]  # add redundant to avoid the bug.
        assert np.ceil(np.log2(vt.size)) == np.log2(vt.size)

        # FFT and linear interpolation.
        vy = time_func(vt)
        freq = np.fft.fftfreq(n_pts)
        vf = np.fft.fft(vy)*np.exp(-2j*np.pi*(t0_ns-pre_pad_len)*freq)
        idx = np.argsort(freq)
        freq = freq[idx]
        vf = vf[idx]
        return np.interp(f,freq,vf.real) + 1j*np.interp(f,freq,vf.imag)

    return Envelope(time_func, freq_func, start=t0, end=t1)

def cosh_CJ(t0_s, amp, width_s=30, plateau_s=4, phase=0, beta=0.0):
    """A rectangular pulse convolved with a gaussian to have smooth rise and fall."""
    t0_ns = t0_s * 1e9
    plateau_ns = plateau_s * 1e9
    width_ns = width_s * 1e9
    tmin = min(t0_ns-(width_ns/2 + plateau_ns/2), t0_ns + width_ns/2 + plateau_ns/2)
    tmax = max(t0_ns-(width_ns/2 + plateau_ns/2), t0_ns + width_ns/2 + plateau_ns/2)

    amp *= np.exp(1j*phase) #np.cos(phase) #
    # _center_pos = t0 + (width + plateau)/2.0

    def timeFunc(t):
        # _x = (np.abs(t - _center_pos) - plateau/2.0)/np.max([1e-11, width])
        # _x[_x<=0] = 0
        # _x[_x>=0.5] = 0.5
        # return amp * (np.cosh(0.5 * beta) - np.cosh(_x * beta)) / (np.cosh(0.5 * beta) - np.cosh(0))
    
        values = np.zeros_like(t) 
        x1 = ( abs(t - t0_ns) <=  plateau_ns/2 + width_ns/2)   
        x2 = ( abs(t - t0_ns) < plateau_ns/2 )
        values[x1] = ( np.cosh(0.5*beta) - np.cosh( (abs(t[x1]-t0_ns)-plateau_ns/2) /width_ns*beta) )/( np.cosh(0.5*beta)-1 )
        values[x2] = 1
        return values * amp

    def freq_func(f):
        # Pad time series for dense frequency points.
        pad_len = 200000
        vt = np.arange(tmin-pad_len, tmax+pad_len)
        # Round size padded time series to power of 2, for sake of faster FFT.
        # BUG: np.ceil(1.000000000000000000000014) = 2. See PEP238.
        n_pts = 2**int(np.ceil(np.log2(vt.size)))
        margin = (n_pts-np.ceil(tmax-tmin)) / 2.
        pre_pad_len = int(np.ceil(margin))
        post_pad_len = int(np.floor(margin))
        vt = np.arange(tmin-pre_pad_len-2, tmax+post_pad_len+2)[:n_pts]  # add redundant to avoid the bug.
        assert np.ceil(np.log2(vt.size)) == np.log2(vt.size)

        # FFT and linear interpolation.
        vy = timeFunc(vt)
        freq = np.fft.fftfreq(n_pts)
        vf = np.fft.fft(vy)*np.exp(-2j*np.pi*(tmin-pre_pad_len)*freq)
        idx = np.argsort(freq)
        freq = freq[idx]
        vf = vf[idx]
        return np.interp(f,freq,vf.real) + 1j*np.interp(f,freq,vf.imag)

    return Envelope(timeFunc, freq_func, start=tmin, end=tmax)


def arb_shape(tp, fp, **kwargs):  # BUG: May generate abnormal waveform 
    t0 = np.min(tp)
    t1 = np.max(tp)
    def time_func(t):
        return np.interp(t, tp, fp, **kwargs)

    def freq_func(f):
        # Pad time series for dense frequency points.
        pad_len = 200000
        vt = np.arange(t0-pad_len, t1+pad_len)
        # Round size padded time series to power of 2, for sake of faster FFT.
        # BUG: np.ceil(1.000000000000000000000014) = 2. See PEP238.
        n_pts = 2**int(np.ceil(np.log2(vt.size)))
        margin = (n_pts-np.ceil(t1-t0)) / 2.
        pre_pad_len = int(np.ceil(margin))
        post_pad_len = int(np.floor(margin))
        vt = np.arange(t0-pre_pad_len-2, t1+post_pad_len+2)[:n_pts]  # add redundant to avoid the bug.
        assert np.ceil(np.log2(vt.size)) == np.log2(vt.size)

        # FFT and linear interpolation.
        vy = time_func(vt)
        freq = np.fft.fftfreq(n_pts)
        vf = np.fft.fft(vy)*np.exp(-2j*np.pi*(t0-pre_pad_len)*freq)
        idx = np.argsort(freq)
        freq = freq[idx]
        vf = vf[idx]
        return np.interp(f,freq,vf.real) + 1j*np.interp(f,freq,vf.imag)
        
    return Envelope(time_func, freq_func, start=t0, end=t1)

# utility functions

def get_slice(t, start, end):
    """Get the slice of an array between start and end.
    
    Assume t is evenly spaced.
    """
    if len(t) < 2:
        return slice(None)
    t0 = t[0]
    dt = t[1] - t0
    if dt == 0:
        return slice(None)
    if start is None:
        s = None
    else:
        if dt > 0:
            s = math.floor((start - t0) / dt)
        else:
            s = math.floor((end - t0) / dt)
        if s < 0:
            s = 0
    if end is None:
        e = None
    else:
        if dt > 0:
            e = math.ceil((end - t0) / dt)
        else:
            e = math.ceil((start - t0) / dt)
        if e < 0:
            e = 0
    return slice(s, e)


def timeRange(envelopes: list[Envelope], default_start=None, default_end=None):
    """Returns the earliest start and latest end of envelopes in floats (without 
    labrad.unit!) The number is in unit of **nano-seconds**, as when defining the 
    envelope. TODO: bad design.

    If no envelopes are given, returns the default_start and default_end.
    """
    starts = [env.start for env in envelopes if env.start is not None]
    start = min(starts) if len(starts) > 0 else default_start
    ends = [env.end for env in envelopes if env.end is not None]
    end = max(ends) if len(ends) > 0 else default_end
    return start, end


def fftFreqs(time=1024):
    """Get a list of frequencies for evaluating fourier envelopes.

    The time is rounded up to the nearest power of two, since powers
    of two are best for the fast fourier transform.  Returns a tuple
    of frequencies to be used for complex and for real signals.
    """
    # nfft = 2**int(math.ceil(math.log(time['ns'], 2)))
    nfft = int(time)
    f_complex = np.fft.fftfreq(nfft)
    f_real = f_complex[:nfft//2+1]
    return f_complex, f_real


def ifft(envelope, t0=-200, n=1000):
    f = np.fft.fftfreq(n)
    return np.fft.ifft(envelope(f, fourier=True) * np.exp(2j*np.pi*t0*f))


def fft(envelope, t0=-200, n=1000):
    t = t0 + np.arange(n)
    return np.fft.fft(envelope(t))


def plotFT(envelope, t0=-200, n=1000):
    t = t0 + np.arange(n)
    y = ifft(envelope, t0, n)
    plt.plot(t, np.real(y))
    plt.plot(t, np.imag(y))


def plotTD(envelope, t0=-200, n=1000):
    t = t0 + np.arange(n)
    y = envelope(t)
    plt.plot(t, np.real(y))
    plt.plot(t, np.imag(y))
