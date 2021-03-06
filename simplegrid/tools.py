"""
Modules containing useful routines

"""

import numpy as np
import os
import datetime
import shutil
from netCDF4 import Dataset


class ShapeError(Exception):
    pass

def get_dt_files(config, minyr, maxyr):
    """ 
    Return dates & filenames matching specified pattern between
    between minyr and maxyr 
    
    """
    files = []
    dts = []
    datadir = config.get('profiles', 'dir')
    fpattern = config.get('profiles', 'fpattern')
    
    for yr in np.arange(minyr, maxyr + 1):
        for mon in np.arange(12) + 1:
            f = datadir + fpattern.replace('${YYYY}', '%4i' % yr)
            f = f.replace('${MM}', '%02i' % mon)
            if os.path.isfile(f):
                dt = datetime.datetime(yr, mon, 1)
                files.append(f)
                dts.append(dt)
                    
    return dts, files


def calc_anom(gridfile, dt, clim):
    """ Calculate anomaly and write to netcdf file """
    
    # Create anomaly file
    anomfile = gridfile.replace('.nc', '_anom_vs_%i-%i.nc' % (clim.minyr, clim.maxyr))
    print 'Writing: %s' % (anomfile)
    shutil.copy(gridfile, anomfile)
    
    # Calculate anomaly
    gridnc = Dataset(gridfile)
    anomnc = Dataset(anomfile, 'r+')
    griddat = gridnc.variables[clim.datavar]
    anomdat = anomnc.variables[clim.datavar]
    anomdat[:] = griddat[:] - clim.grid_mean[dt.month - 1]
    
    # Close files
    gridnc.close()
    anomnc.close()
    

    