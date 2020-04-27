# -*- coding: utf-8 -*-
"""
Bayesian Inverse Fourier Transform

This code is the implementation of 
Steen Hansen J. Appl. Cryst. (2000). 33, 1415-1421

Based on the BIFT from Jesse Hopkins, available at:
https://sourceforge.net/p/bioxtasraw/git/ci/master/tree/bioxtasraw/BIFT.py

Many thanks to Pierre Paleo for the auto-alpha guess
"""

__authors__ = ["Jerome Kieffer", "Jesse Hopkins"]
__license__ = "MIT"
__copyright__ = "2020, ESRF"
__date__ = "27/04/2020"

import logging
logger = logging.getLogger(__name__)
from collections import namedtuple
from math import log
import numpy
from scipy.optimize import minimize
from ._bift import BIFT
from .autorg import autoRg
from .decorators import timeit

IFT_RESULT = namedtuple("IFT_RESULT", "r p sigma Dmax alpha logP chi2 regularisation")


@timeit
def auto_bift(data, Dmax=None, alpha=None, npt=100, start_point=None, end_point=None):
    """Calculates the inverse Fourier tranform of the data
    
    :param data: 2D array with q, I(q), δI(q). q can be in 1/nm or 1/A, it imposes the unit for r & Dmax
    :param Dmax: Maximum diameter of the object, this is the starting point to be refined. Can be guessed
    :param alpha: Regularisation parameter, let it to None for automatic scan
    :param npt: Number of point for the curve p(r)
    :param start_point: First useable point in the I(q) curve
    :param end_point: Last useable point in the I(q) curve
    :return: IFT_RESULT instance with the result p(r) in it
    """
    assert data.ndim == 2
    assert data.shape[1] == 3  # enforce q, I, err
    data = data[slice(start_point, end_point)]
    q, I, err = data.T
    npt = min(npt, q.size)  # no chance for oversampling !
    bo = BIFT(q, I, err)  # this is the bift object
    if Dmax is None:
        # Try to get a reasonable from Rg
        rg = autoRg(data)
        bo.set_Guinier(rg)
        Dmax = bo.Dmax_guess
    if alpha is None:
        Niter = 9  # odd value to have 1 in the loop
        alpha_max = bo.guess_alpha_max(npt)
        alpha = bo.grid_scan(Dmax, Dmax, 1, 1.0 / alpha_max, alpha_max, Niter, npt)[1]

    # Optimization using Bayesian operator:
    logger.debug("start search at alpha=%s Dmax=%s", alpha, Dmax)
    res = minimize(bo.opti_evidence, (Dmax, log(alpha)), args=(npt,), method="powell")
    print(res)
    print("*"*50)
    # res = minimize(bo.opti_evidence, res.x, args=(npt,), method="slsqp", options={"eps":1e-2}, bounds=[(1 / bo.q[-1], 1 / bo.delta_q), (0, 2 * alpha_max)])
    print(bo.calc_stats())
    return bo


if __name__ == "__main__":
    import sys
    data = numpy.loadtxt(sys.argv[1])

