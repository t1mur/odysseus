import numpy as np


from pluginmanager import DialogPlugin
from imageprocess import radial_interpolate
from fitfermions import norm_and_guess
from fitfuncs import *

class GaussianFitPlugin(DialogPlugin):
    """Integrates image along one axis and fits a gaussian"""

    def main(self, img):
        """Integrate along one axis and display the resulting linear profile"""
        
        transimg, odimg, com, n0, a, bprime = norm_and_guess(img)
        #line_profile_x = np.sum(odimg, 0)
        #line_coord_x = range(len(line_profile_x))
        #N_count = np.sum(line_profile_x)
        #peak_x = np.argmax(line_profile_x)
        #ans = fit1dfunc(gaussian, line_coord_x, \
                        #line_profile_x, [n0, bprime, com[0]])
        #fit_profile_x = gaussian(line_coord_x, ans[0], ans[1], ans[2])
        
        line_profile_y = np.sum(odimg, 1)
        line_coord_y = range(len(line_profile_y))
        N_count = np.sum(line_profile_y)
        peak_y = np.argmax(line_profile_y)
        ans1 = fit1dfunc(gaussian, line_coord_y, \
                        line_profile_y, [n0, bprime, com[0]])
        fit_profile_y = gaussian(line_coord_y, ans1[0], ans1[1], ans1[2])
        
        #self.ax.plot(line_coord_x, line_profile_x)
        #self.ax.plot(line_coord_x, fit_profile_x, 'r-')
        #self.ax.set_xlabel(r'pix')
        #self.ax.set_ylabel(r'OD')
        #self.ax.set_title(r'X vs. Integrated OD')
        #self.ax.text(len(line_profile_x)*0.65, line_coord_x[peak_x], 'width = %1.2f'%(ans[1]/1.414))
        #self.ax.text(len(line_profile_x)*0.75, line_coord_x[peak_x]*0.9, 'N = %1.2f'%(N_count))
       
        self.ax.plot(line_coord_y, line_profile_y)
        self.ax.plot(line_coord_y, fit_profile_y, 'r-')
        self.ax.set_xlabel(r'pix')
        self.ax.set_ylabel(r'OD')
        self.ax.set_title(r'Y vs. Integrated OD')
        self.ax.text(len(line_profile_y)*0.65, line_coord_y[peak_y], 'width = %1.2f'%(ans1[1]/1.414))
        self.ax.text(len(line_profile_y)*0.75, line_coord_y[peak_y]*0.9, 'N = %1.2f'%(N_count))