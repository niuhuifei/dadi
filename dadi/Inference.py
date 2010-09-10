"""
Comparison and optimization of model spectra to data.
"""
import logging
logger = logging.getLogger('Inference')

import numpy
from numpy import logical_and, logical_not

from dadi import Misc, Numerics
from scipy.special import gammaln
import scipy.optimize

#: Counts calls to object_func
_counter = 0
#: Returned when object_func is passed out-of-bounds params or gets a NaN ll.
_out_of_bounds_val = -1e8
def _object_func(params, data, model_func, pts, 
                 lower_bound=None, upper_bound=None, 
                 verbose=0, multinom=True, flush_delay=0,
                 func_args=[], fixed_params=None, ll_scale=1):
    """
    Objective function for optimization.
    """
    global _counter
    _counter += 1

    # Deal with fixed parameters
    params = _project_params_up(params, fixed_params)

    # Check our parameter bounds
    if lower_bound is not None:
        for pval,bound in zip(params, lower_bound):
            if bound is not None and pval < bound:
                return -_out_of_bounds_val/ll_scale
    if upper_bound is not None:
        for pval,bound in zip(params, upper_bound):
            if bound is not None and pval > bound:
                return -_out_of_bounds_val/ll_scale

    ns = data.sample_sizes 
    all_args = [params, ns] + list(func_args) + [pts]
    sfs = model_func(*all_args)
    if multinom:
        result = ll_multinom(sfs, data)
    else:
        result = ll(sfs, data)

    # Bad result
    if numpy.isnan(result):
        result = _out_of_bounds_val

    if (verbose > 0) and (_counter % verbose == 0):
        param_str = 'array([%s])' % (', '.join(['%- 12g'%v for v in params]))
        print '%-8i, %-12g, %s' % (_counter, result, param_str)
        Misc.delayed_flush(delay=flush_delay)

    return -result/ll_scale

def _object_func_log(log_params, *args, **kwargs):
    """
    Objective function for optimization in log(params).
    """
    return _object_func(numpy.exp(log_params), *args, **kwargs)

def optimize_log(p0, data, model_func, pts, lower_bound=None, upper_bound=None,
                 verbose=0, flush_delay=0.5, epsilon=1e-3, 
                 pgtol=1e-5, multinom=True, maxiter=1e5, full_output=False,
                 func_args=[], fixed_params=None, ll_scale=1):
    """
    Optimize log(params) to fit model to data using the L-BFGS-B method.

    This optimization method works well when we start reasonably close to the
    optimum. It is best at burrowing down a single minimum.

    Because this works in log(params), it cannot explore values of params < 0.
    It should also perform better when parameters range over scales.

    p0: Initial parameters.
    data: Spectrum with data.
    model_function: Function to evaluate model spectrum. Should take arguments
                    (params, (n1,n2...), pts)
    lower_bound: Lower bound on parameter values. If not None, must be of same
                 length as p0. A parameter can be declared unbound by assigning
                 a bound of None.
    upper_bound: Upper bound on parameter values. If not None, must be of same
                 length as p0. A parameter can be declared unbound by assigning
                 a bound of None.
    verbose: If > 0, print optimization status every <verbose> steps.
    flush_delay: Standard output will be flushed once every <flush_delay>
                 minutes. This is useful to avoid overloading I/O on clusters.
    epsilon: Step-size to use for finite-difference derivatives.
    pgtol: Convergence criterion for optimization. For more info, 
          see help(scipy.optimize.fmin_l_bfgs_b)
    multinom: If True, do a multinomial fit where model is optimially scaled to
              data at each step. If False, assume theta is a parameter and do
              no scaling.
    maxiter: Maximum algorithm iterations to run.
    full_output: If True, return full outputs as in described in 
                 help(scipy.optimize.fmin_bfgs)
    func_args: Additional arguments to model_func. It is assumed that 
               model_func's first argument is an array of parameters to
               optimize, that its second argument is an array of sample sizes
               for the sfs, and that its last argument is the list of grid
               points to use in evaluation.
    fixed_params: If not None, should be a list used to fix model parameters at
                  particular values. For example, if the model parameters
                  are (nu1,nu2,T,m), then fixed_params = [0.5,None,None,2]
                  will hold nu1=0.5 and m=2. The optimizer will only change 
                  T and m. Note that the bounds lists must include all
                  parameters. Optimization will fail if the fixed values
                  lie outside their bounds. A full-length p0 should be passed
                  in; values corresponding to fixed parameters are ignored.
    ll_scale: The bfgs algorithm may fail if your initial log-likelihood is
              too large. (This appears to be a flaw in the scipy
              implementation.) To overcome this, pass ll_scale > 1, which will
              simply reduce the magnitude of the log-likelihood. Once in a
              region of reasonable likelihood, you'll probably want to
              re-optimize with ll_scale=1.

    The L-BFGS-B method was developed by Ciyou Zhu, Richard Byrd, and Jorge
    Nocedal. The algorithm is described in:
      * R. H. Byrd, P. Lu and J. Nocedal. A Limited Memory Algorithm for Bound
        Constrained Optimization, (1995), SIAM Journal on Scientific and
        Statistical Computing , 16, 5, pp. 1190-1208.
      * C. Zhu, R. H. Byrd and J. Nocedal. L-BFGS-B: Algorithm 778: L-BFGS-B,
        FORTRAN routines for large scale bound constrained optimization (1997),
        ACM Transactions on Mathematical Software, Vol 23, Num. 4, pp. 550-560.
    
    """
    args = (data, model_func, pts, None, None, verbose,
            multinom, flush_delay, func_args, fixed_params, ll_scale)

    # Make bounds list. For this method it needs to be in terms of log params.
    if lower_bound is None:
        lower_bound = [None] * len(p0)
    else:
        lower_bound = numpy.log(lower_bound)
        lower_bound[numpy.isnan(lower_bound)] = None
    lower_bound = _project_params_down(lower_bound, fixed_params)
    if upper_bound is None:
        upper_bound = [None] * len(p0)
    else:
        upper_bound = numpy.log(upper_bound)
        upper_bound[numpy.isnan(upper_bound)] = None
    upper_bound = _project_params_down(upper_bound, fixed_params)
    bounds = list(zip(lower_bound,upper_bound))

    p0 = _project_params_down(p0, fixed_params)

    outputs = scipy.optimize.fmin_l_bfgs_b(_object_func_log, 
                                           numpy.log(p0), bounds = bounds,
                                           epsilon=epsilon, args = args,
                                           iprint = -1, pgtol=pgtol,
                                           maxfun=maxiter, approx_grad=True)
    xopt, fopt, info_dict = outputs

    xopt = _project_params_up(numpy.exp(xopt), fixed_params)

    if not full_output:
        return xopt
    else:
        return xopt, fopt, info_dict

def minus_ll(model, data):
    """
    The negative of the log-likelihood of the data given the model sfs.
    """
    return -ll(model, data)

def ll(model, data):
    """
    The log-likelihood of the data given the model sfs.

    Evaluate the log-likelihood of the data given the model. This is based on
    Poisson statistics, where the probability of observing k entries in a cell
    given that the mean number is given by the model is 
    P(k) = exp(-model) * model**k / k!

    Note: If either the model or the data is a masked array, the return ll will
          ignore any elements that are masked in *either* the model or the data.
    """
    ll_arr = ll_per_bin(model, data)
    return ll_arr.sum()

def ll_per_bin(model, data):
    """
    The Poisson log-likelihood of each entry in the data given the model sfs.
    """
    if data.folded and not model.folded:
        model = model.fold()

    if numpy.any(logical_and(model < 0, logical_not(data.mask))):
        logger.warn('Model is < 0 where data is not masked.')
    # If the data is 0, it's okay for the model to be 0. In that case the ll
    # contribution is 0, which is fine.
    if numpy.any(logical_and(model == 0, 
                             logical_and(data > 0, logical_not(data.mask)))):
        logger.warn('Model is 0 where data is neither masked nor 0.')
    if numpy.any(numpy.logical_and(model.mask, numpy.logical_not(data.mask))):
        logger.warn('Model is masked in some entries where data is not.')
    if numpy.any(numpy.logical_and(numpy.isnan(model), 
                                   numpy.logical_not(data.mask))):
        logger.warn('Model is nan in some entries where data is not masked.')

    return -model + data*numpy.ma.log(model) - gammaln(data + 1.)

def ll_multinom_per_bin(model, data):
    """
    Mutlinomial log-likelihood of each entry in the data given the model.

    Scales the model sfs to have the optimal theta for comparison with the data.
    """
    theta_opt = optimal_sfs_scaling(model, data)
    return ll_per_bin(theta_opt*model, data)

def ll_multinom(model, data):
    """
    Log-likelihood of the data given the model, with optimal rescaling.

    Evaluate the log-likelihood of the data given the model. This is based on
    Poisson statistics, where the probability of observing k entries in a cell
    given that the mean number is given by the model is 
    P(k) = exp(-model) * model**k / k!

    model is optimally scaled to maximize ll before calculation.

    Note: If either the model or the data is a masked array, the return ll will
          ignore any elements that are masked in *either* the model or the data.
    """
    ll_arr = ll_multinom_per_bin(model, data)
    return ll_arr.sum()

def minus_ll_multinom(model, data):
    """
    The negative of the log-likelihood of the data given the model sfs.

    Return a double that is -(log-likelihood)
    """
    return -ll_multinom(model, data)

def linear_Poisson_residual(model, data, mask=None):
    """
    Return the Poisson residuals, (model - data)/sqrt(model), of model and data.

    mask sets the level in model below which the returned residual array is
    masked. The default of 0 excludes values where the residuals are not 
    defined.

    In the limit that the mean of the Poisson distribution is large, these
    residuals are normally distributed. (If the mean is small, the Anscombe
    residuals are better.)
    """
    if data.folded and not model.folded:
        model = model.fold()

    resid = (model - data)/numpy.ma.sqrt(model)
    if mask is not None:
        tomask = numpy.logical_and(model <= mask, data <= mask)
        resid = numpy.ma.masked_where(tomask, resid)
    return resid

def Anscombe_Poisson_residual(model, data, mask=None):
    """
    Return the Anscombe Poisson residuals between model and data.

    mask sets the level in model below which the returned residual array is
    masked. This excludes very small values where the residuals are not normal.
    1e-2 seems to be a good default for the NIEHS human data. (model = 1e-2,
    data = 0, yields a residual of ~1.5.)

    Residuals defined in this manner are more normally distributed than the
    linear residuals when the mean is small. See this reference below for
    justification: Pierce DA and Schafer DW, "Residuals in generalized linear
    models" Journal of the American Statistical Association, 81(396)977-986
    (1986).

    Note that I tried implementing the "adjusted deviance" residuals, but they
    always looked very biased for the cases where the data was 0.
    """
    if data.folded and not model.folded:
        model = model.fold()
    # Because my data have often been projected downward or averaged over many
    # iterations, it appears better to apply the same transformation to the data
    # and the model.
    # For some reason data**(-1./3) results in entries in data that are zero
    # becoming masked. Not just the result, but the data array itself. We use
    # the power call to get around that.
    # This seems to be a common problem, that we want to use numpy.ma functions
    # on masked arrays, because otherwise the mask on the input itself can be
    # changed. Subtle and annoying. If we need to create our own functions, we
    # can use numpy.ma.core._MaskedUnaryOperation.
    datatrans = data**(2./3) - numpy.ma.power(data,-1./3)/9
    modeltrans = model**(2./3) - numpy.ma.power(model,-1./3)/9
    resid = 1.5*(datatrans - modeltrans)/model**(1./6)
    if mask is not None:
        tomask = numpy.logical_and(model <= mask, data <= mask)
        tomask = numpy.logical_or(tomask, data == 0)
        resid = numpy.ma.masked_where(tomask, resid)
    # It makes more sense to me to have a minus sign here... So when the
    # model is high, the residual is positive. This is opposite of the
    # Pierce and Schafner convention.
    return -resid

def optimally_scaled_sfs(model, data):
    """
    Optimially scale model sfs to data sfs.

    Returns a new scaled model sfs.
    """
    return optimal_sfs_scaling(model,data) * model

def optimal_sfs_scaling(model, data):
    """
    Optimal multiplicative scaling factor between model and data.

    This scaling is based on only those entries that are masked in neither
    model nor data.
    """
    if data.folded and not model.folded:
        model = model.fold()

    model, data = Numerics.intersect_masks(model, data)
    return data.sum()/model.sum()

def optimize_log_fmin(p0, data, model_func, pts, 
                      lower_bound=None, upper_bound=None,
                      verbose=0, flush_delay=0.5, 
                      multinom=True, maxiter=None, 
                      full_output=False, func_args=[], 
                      fixed_params=None):
    """
    Optimize log(params) to fit model to data using Nelder-Mead. 

    This optimization method make work better than BFGS when far from a
    minimum. It is much slower, but more robust, because it doesn't use
    gradient information.

    Because this works in log(params), it cannot explore values of params < 0.
    It should also perform better when parameters range over large scales.

    p0: Initial parameters.
    data: Spectrum with data.
    model_function: Function to evaluate model spectrum. Should take arguments
                    (params, (n1,n2...), pts)
    lower_bound: Lower bound on parameter values. If not None, must be of same
                 length as p0. A parameter can be declared unbound by assigning
                 a bound of None.
    upper_bound: Upper bound on parameter values. If not None, must be of same
                 length as p0. A parameter can be declared unbound by assigning
                 a bound of None.
    verbose: If True, print optimization status every <verbose> steps.
    flush_delay: Standard output will be flushed once every <flush_delay>
                 minutes. This is useful to avoid overloading I/O on clusters.
    multinom: If True, do a multinomial fit where model is optimially scaled to
              data at each step. If False, assume theta is a parameter and do
              no scaling.
    maxiter: Maximum iterations to run for.
    full_output: If True, return full outputs as in described in 
                 help(scipy.optimize.fmin_bfgs)
    func_args: Additional arguments to model_func. It is assumed that 
               model_func's first argument is an array of parameters to
               optimize, that its second argument is an array of sample sizes
               for the sfs, and that its last argument is the list of grid
               points to use in evaluation.
    fixed_params: If not None, should be a list used to fix model parameters at
                  particular values. For example, if the model parameters
                  are (nu1,nu2,T,m), then fixed_params = [0.5,None,None,2]
                  will hold nu1=0.5 and m=2. The optimizer will only change 
                  T and m. Note that the bounds lists must include all
                  parameters. Optimization will fail if the fixed values
                  lie outside their bounds. A full-length p0 should be passed
                  in; values corresponding to fixed parameters are ignored.
    """
    args = (data, model_func, pts, lower_bound, upper_bound, verbose,
            multinom, flush_delay, func_args, fixed_params, 1.0)

    p0 = _project_params_down(p0, fixed_params)
    outputs = scipy.optimize.fmin(_object_func_log, numpy.log(p0), args = args,
                                  disp=False, maxiter=maxiter, full_output=True)
    xopt, fopt, iter, funcalls, warnflag = outputs
    xopt = _project_params_up(numpy.exp(xopt), fixed_params)

    if not full_output:
        return xopt
    else:
        return xopt, fopt, iter, funcalls, warnflag 

def optimize(p0, data, model_func, pts, lower_bound=None, upper_bound=None,
             verbose=0, flush_delay=0.5, epsilon=1e-3, 
             pgtol=1e-5, multinom=True, maxiter=1e5, full_output=False,
             func_args=[], fixed_params=None, ll_scale=1):
    """
    Optimize log(params) to fit model to data using the L-BFGS-B method.

    This optimization method works well when we start reasonably close to the
    optimum. It is best at burrowing down a single minimum.

    p0: Initial parameters.
    data: Spectrum with data.
    model_function: Function to evaluate model spectrum. Should take arguments
                    (params, (n1,n2...), pts)
    lower_bound: Lower bound on parameter values. If not None, must be of same
                 length as p0. A parameter can be declared unbound by assigning
                 a bound of None.
    upper_bound: Upper bound on parameter values. If not None, must be of same
                 length as p0. A parameter can be declared unbound by assigning
                 a bound of None.
    verbose: If > 0, print optimization status every <verbose> steps.
    flush_delay: Standard output will be flushed once every <flush_delay>
                 minutes. This is useful to avoid overloading I/O on clusters.
    epsilon: Step-size to use for finite-difference derivatives.
    pgtol: Convergence criterion for optimization. For more info, 
          see help(scipy.optimize.fmin_l_bfgs_b)
    multinom: If True, do a multinomial fit where model is optimially scaled to
              data at each step. If False, assume theta is a parameter and do
              no scaling.
    maxiter: Maximum algorithm iterations evaluations to run.
    full_output: If True, return full outputs as in described in 
                 help(scipy.optimize.fmin_bfgs)
    func_args: Additional arguments to model_func. It is assumed that 
               model_func's first argument is an array of parameters to
               optimize, that its second argument is an array of sample sizes
               for the sfs, and that its last argument is the list of grid
               points to use in evaluation.
    fixed_params: If not None, should be a list used to fix model parameters at
                  particular values. For example, if the model parameters
                  are (nu1,nu2,T,m), then fixed_params = [0.5,None,None,2]
                  will hold nu1=0.5 and m=2. The optimizer will only change 
                  T and m. Note that the bounds lists must include all
                  parameters. Optimization will fail if the fixed values
                  lie outside their bounds. A full-length p0 should be passed
                  in; values corresponding to fixed parameters are ignored.
    ll_scale: The bfgs algorithm may fail if your initial log-likelihood is
              too large. (This appears to be a flaw in the scipy
              implementation.) To overcome this, pass ll_scale > 1, which will
              simply reduce the magnitude of the log-likelihood. Once in a
              region of reasonable likelihood, you'll probably want to
              re-optimize with ll_scale=1.

    The L-BFGS-B method was developed by Ciyou Zhu, Richard Byrd, and Jorge
    Nocedal. The algorithm is described in:
      * R. H. Byrd, P. Lu and J. Nocedal. A Limited Memory Algorithm for Bound
        Constrained Optimization, (1995), SIAM Journal on Scientific and
        Statistical Computing , 16, 5, pp. 1190-1208.
      * C. Zhu, R. H. Byrd and J. Nocedal. L-BFGS-B: Algorithm 778: L-BFGS-B,
        FORTRAN routines for large scale bound constrained optimization (1997),
        ACM Transactions on Mathematical Software, Vol 23, Num. 4, pp. 550-560.
    """
    args = (data, model_func, pts, None, None, verbose,
            multinom, flush_delay, func_args, fixed_params, ll_scale)

    # Make bounds list. For this method it needs to be in terms of log params.
    if lower_bound is None:
        lower_bound = [None] * len(p0)
    lower_bound = _project_params_down(lower_bound, fixed_params)
    if upper_bound is None:
        upper_bound = [None] * len(p0)
    upper_bound = _project_params_down(upper_bound, fixed_params)
    bounds = list(zip(lower_bound,upper_bound))

    p0 = _project_params_down(p0, fixed_params)

    outputs = scipy.optimize.fmin_l_bfgs_b(_object_func, 
                                           numpy.log(p0), bounds=bounds,
                                           epsilon=epsilon, args=args,
                                           iprint=-1, pgtol=pgtol,
                                           maxfun=maxiter, approx_grad=True)
    xopt, fopt, info_dict = outputs

    xopt = _project_params_up(xopt, fixed_params)

    if not full_output:
        return xopt
    else:
        return xopt, fopt, info_dict

def _project_params_down(pin, fixed_params):
    """
    Eliminate fixed parameters from pin.
    """
    if fixed_params is None:
        return pin

    if len(pin) != len(fixed_params):
        raise ValueError('fixed_params list must have same length as input '
                         'parameter array.')

    pout = []
    for ii, (curr_val,fixed_val) in enumerate(zip(pin, fixed_params)):
        if fixed_val is None:
            pout.append(curr_val)

    return numpy.array(pout)

def _project_params_up(pin, fixed_params):
    """
    Fold fixed parameters into pin.
    """
    if fixed_params is None:
        return pin

    pout = numpy.zeros(len(fixed_params))
    orig_ii = 0
    for out_ii, val in enumerate(fixed_params):
        if val is None:
            pout[out_ii] = pin[orig_ii]
            orig_ii += 1
        else:
            pout[out_ii] = fixed_params[out_ii]
    return pout

index_exp = numpy.index_exp
def optimize_grid(data, model_func, pts, grid,
                  verbose=0, flush_delay=0.5,
                  multinom=True, full_output=False,
                  func_args=[], fixed_params=None):
    """
    Optimize params to fit model to data using brute force search over a grid.

    data: Spectrum with data.
    model_func: Function to evaluate model spectrum. Should take arguments
                (params, (n1,n2...), pts)
    pts: Grid points list for evaluating likelihoods
    grid: Grid of parameter values over which to evaluate likelihood. See
          below for specification instructions.
    verbose: If > 0, print optimization status every <verbose> steps.
    flush_delay: Standard output will be flushed once every <flush_delay>
                 minutes. This is useful to avoid overloading I/O on clusters.
    multinom: If True, do a multinomial fit where model is optimially scaled to
              data at each step. If False, assume theta is a parameter and do
              no scaling.
    full_output: If True, return full outputs as in described in 
                 help(scipy.optimize.brute)
    func_args: Additional arguments to model_func. It is assumed that 
               model_func's first argument is an array of parameters to
               optimize, that its second argument is an array of sample sizes
               for the sfs, and that its last argument is the list of grid
               points to use in evaluation.
    fixed_params: If not None, should be a list used to fix model parameters at
                  particular values. For example, if the model parameters
                  are (nu1,nu2,T,m), then fixed_params = [0.5,None,None,2]
                  will hold nu1=0.5 and m=2. The optimizer will only change 
                  T and m. Note that the bounds lists must include all
                  parameters. Optimization will fail if the fixed values
                  lie outside their bounds. A full-length p0 should be passed
                  in; values corresponding to fixed parameters are ignored.

    Search grids are specified using a dadi.Inference.index_exp object (which
    is an alias for numpy.index_exp). The grid is specified by passing a range
    of values for each parameter. For example, index_exp[0:1.1:0.3,
    0.7:0.9:11j] will search over parameter 1 with values 0,0.3,0.6,0.9 and
    over parameter 2 with 11 points between 0.7 and 0.9 (inclusive). (Notice
    the 11j in the second parameter range specification.) Note that the grid
    list should include only parameters that are optimized over, not fixed
    parameter values.
    """
    args = (data, model_func, pts, None, None, verbose,
            multinom, flush_delay, func_args, fixed_params, 1.0)

    outputs = scipy.optimize.brute(_object_func, ranges=grid,
                                   args = args, full_output=full_output)
    if full_output:
        xopt, fopt, grid, fout = outputs
    else:
        xopt = outputs
    xopt = _project_params_up(xopt, fixed_params)

    if not full_output:
        return xopt
    else:
        return xopt, fopt, grid, fout
