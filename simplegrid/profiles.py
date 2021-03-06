""" Module containing class to load and aggregate profile data """ 

from netCDF4 import Dataset, date2num
import numpy as np
import scipy.stats
import time

class ShapeError(Exception):
    pass

class Profiles(object):
    """ Class containing methods to read and manipulate profile data """ 
    
    def __init__(self, config, fname, dt, preload=True):
        """ Initialize using configuration options """ 
        
        self.config = config
        self.fname = fname
        self.dt = dt
        self.xvar = config.get('profiles', 'xvar')
        self.yvar = config.get('profiles', 'yvar')
        self.zvar = config.get('profiles', 'zvar')
        self.qcvar = config.get('profiles', 'qcvar')
        self.posqcvar = config.get('profiles', 'posqcvar')
        self.datavar = config.get('profiles', 'datavar')
        
        if preload: 
            self.load_data()
            self.load_x()
            self.load_y()
            self.load_z()
            self.load_qc()
            self.load_posqc()
            
    def read_var(self, ncvar):
        """ Read data from specified variable """
        ncf = Dataset(self.fname)
        dat = ncf.variables[ncvar][:]
        ncf.close()
        return dat   
                       
    def load_x(self):
        """ Load x-coordinate data as <np.array> """
        self.x = self.read_var(self.xvar)
        self.test_shape(self.xvar, self.x.shape, 1)
        
    def load_y(self):
        """ Load y-coordinate data as <np.array> """
        self.y = self.read_var(self.yvar)
        self.test_shape(self.yvar, self.y.shape, 1)

    def load_z(self):
        """ Load z-coordinate data as <np.array> """
        self.z = self.read_var(self.zvar)
        self.test_shape(self.zvar, self.z.shape, 2)
        
    def load_data(self):
        """ Load profile data as <np.array> """
        self.data = self.read_var(self.datavar)
        self.test_shape(self.datavar, self.data.shape, 2)    
        
    def load_qc(self):
        """ Load data quality control flags as <np.array> """
        rejectval = self.config.get('profiles', 'qcreject')        
        self.qc = self.read_var(self.qcvar) != rejectval
        self.test_shape(self.qcvar, self.qc.shape, 2)
        
    def load_posqc(self):
        """ Load position quality control flags as <np.array> """
        rejectval = self.config.get('profiles', 'posqcreject')        
        self.posqc = self.read_var(self.posqcvar) != rejectval
        self.test_shape(self.posqcvar, self.posqc.shape, 1)          
        
    def test_shape(self, varname, varshape, ndim):
        """ Raise error if shape unexpected """ 
        if len(varshape) != ndim:
            raise ShapeError('Shape=%s. Expected %i-D array for %s' %
                              (repr(varshape), ndim, varname))
    
    def reshape_1d(self, dat):
        """ Reshape data into 1d arrays """
        if dat.ndim == 1:
            dat = np.ones_like(self.data) * dat[:, np.newaxis]
            
        if (dat.shape != self.data.shape):
            raise ShapeError('%s != %s: reshaped variables must have same shape as data.' 
                             % (repr(dat.shape), repr(self.data.shape)))

        try: 
            mask = self.data.mask
            dat = dat[mask == False]
        except AttributeError:
            pass
        
        dat = np.reshape(dat, dat.size)
        
        return dat
    
    def grid_data(self, method='mean'):
        """ Grid data using specifications in config attribute """ 

        # Reshape
        self.data_1d = self.reshape_1d(self.data)
        self.x_1d = self.reshape_1d(self.x)
        self.y_1d = self.reshape_1d(self.y)
        self.z_1d = self.reshape_1d(self.z)
        self.qc_1d = self.reshape_1d(self.qc)
        self.posqc_1d = self.reshape_1d(self.posqc)
        
        # Apply QC
        qcind = (self.qc_1d == True) & (self.posqc_1d == True)
        self.qc_1d = self.qc_1d[qcind]
        self.posqc_1d = self.posqc_1d[qcind]
        self.data_1d = self.data_1d[qcind]
        self.x_1d = self.x_1d[qcind]
        self.y_1d = self.y_1d[qcind]
        self.z_1d = self.z_1d[qcind]

        # Prepare data for gridding
        self.init_xgrid()
        self.init_ygrid()
        self.init_zgrid()
        points = np.vstack([self.z_1d, self.y_1d, self.x_1d]).transpose()
        bins = [self.zbounds, self.ybounds, self.xbounds]
        
        # Grid data
        grid_count, binedges, binno = scipy.stats.binned_statistic_dd(
            points, self.data_1d, statistic='count', bins=bins)
        grid_sum, binedges, binno = scipy.stats.binned_statistic_dd(
            points, self.data_1d, statistic='sum', bins=bins)
        
        grid_mean = grid_sum / grid_count
        grid_mean = np.ma.MaskedArray(grid_mean, mask = (grid_count == 0))
        self.grid_mean = grid_mean
        self.grid_count = grid_count
        self.grid_sum = grid_sum

    def create_savename(self):
        """ Generate file name based on file name and grid specification """
        
        savename = self.config.get('grid', 'dir') + self.fname.split('/')[-1]
        newsuffix = '_gridded_%ix%ix%i.nc' % (self.nx, self.ny, self.nz)
        savename = savename.replace('.nc', newsuffix)
        
        return savename

    def write_grid(self):
        """ Write gridded data to netcdf  """
        
        self.fout = self.create_savename()
        ncout = Dataset(self.fout, 'w')
        print 'Writing: %s' % self.fout
        
        # Create dimensions
        xdim = ncout.createDimension(self.xvar, self.nx)
        ydim = ncout.createDimension(self.yvar, self.ny)
        zdim = ncout.createDimension(self.zvar, self.nz) 
        tdim = ncout.createDimension('time', None) 

        # Create variables
        varx = ncout.createVariable(self.xvar, 'float64', (self.xvar,))
        varxmin = ncout.createVariable('%s_minbounds' % (self.xvar), 'float32', (self.xvar,))
        varxmax = ncout.createVariable('%s_maxbounds' % (self.xvar), 'float32', (self.xvar,))
        vary = ncout.createVariable(self.yvar, 'float64', (self.yvar,))
        varymin = ncout.createVariable('%s_minbounds' % (self.yvar), 'float32', (self.yvar,))
        varymax = ncout.createVariable('%s_maxbounds' % (self.yvar), 'float32', (self.yvar,))
        varz = ncout.createVariable(self.zvar, 'float64', (self.zvar,))
        varzmin = ncout.createVariable('%s_minbounds' % (self.zvar), 'float32', (self.zvar,))
        varzmax = ncout.createVariable('%s_maxbounds' % (self.zvar), 'float32', (self.zvar,))
        varmean = ncout.createVariable(self.datavar, 'float32', ('time',self.zvar,self.yvar,self.xvar))
        varsum = ncout.createVariable('sum', 'float32', ('time',self.zvar,self.yvar,self.xvar))
        varcount = ncout.createVariable('count', 'float32', ('time',self.zvar,self.yvar,self.xvar))
        vartime = ncout.createVariable('time', 'float64', ('time',))
        vartime.units = 'hours since 0001-01-01 00:00:00'
        vartime.calendar = 'gregorian'

        # Write to variables
        varx[:] = self.xgrid
        varxmin[:] = self.xminbounds
        varxmax[:] = self.xmaxbounds
        vary[:] = self.ygrid
        varymin[:] = self.yminbounds
        varymax[:] = self.ymaxbounds
        varz[:] = self.zgrid
        varzmin[:] = self.zminbounds
        varzmax[:] = self.zmaxbounds
        varmean[:] = self.grid_mean[np.newaxis]
        varsum[:] = self.grid_sum[np.newaxis]
        varcount[:] = self.grid_count[np.newaxis]
        vartime[:] = date2num(self.dt, units=vartime.units, calendar=vartime.calendar)
        
        # Add  global attributes
        ncout.history = 'Created ' + time.ctime(time.time())
        
        # Save
        ncout.close()  
    
    def init_xgrid(self):
        """ Initialize x dimension """
        dx = self.config.getfloat('grid', 'dx')
        xmin = self.config.getfloat('grid', 'xmin')
        xmax = self.config.getfloat('grid', 'xmax')
        self.xbounds = np.arange(xmin, xmax+dx, dx)
        self.xminbounds = self.xbounds[:-1]
        self.xmaxbounds = self.xbounds[1:]
        self.xgrid = 0.5 * (self.xminbounds + self.xmaxbounds)
        self.nx = len(self.xgrid)

    def init_ygrid(self):
        """ Initialize y dimension """
        dy = self.config.getfloat('grid', 'dy')
        ymin = self.config.getfloat('grid', 'ymin')
        ymax = self.config.getfloat('grid', 'ymax')
        self.ybounds = np.arange(ymin, ymax + dy, dy) 
        self.yminbounds = self.ybounds[:-1]
        self.ymaxbounds = self.ybounds[1:]
        self.ygrid = 0.5 * (self.yminbounds + self.ymaxbounds)
        self.ny = len(self.ygrid)

    def init_zgrid(self):
        """ Initialize y dimension """
        self.zbounds = np.array(self.config.get('grid', 'zbounds').split(','), dtype=np.float64)
        self.zminbounds = self.zbounds[:-1]
        self.zmaxbounds = self.zbounds[1:]
        self.zgrid = 0.5 * (self.zminbounds + self.zmaxbounds)
        self.nz = len(self.zgrid)


