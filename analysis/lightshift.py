import numpy as np
import scipy as sp

from constants import *


def acstark(w_laser, w_atom, power, waist, linewidth):
    """The ac Stark shift, without the rotating wave approximation.

    **Inputs**

      * w_laser: float, laser wavelength in meters
      * w_atom: float, resonant wavelength for the atom. For very large
                detuning, this is the middle between the D1 and D2 lines.
      * power: float, laser power in Watts
      * waist: float, waist size (i.e. 1/e^2 radius) of the laser beam in meters
      * linewidth: float, linewidth for the atomic transition (usually the one
                   for the D2 line if an alkali atom) in Hz (not rad/s!)


    **Outputs**

      * acshift: float, the ac Stark shift

    **Notes**

    The detuning is so large that the rotating wave approximation is invalid.

    """

    lw = linewidth*2*np.pi # to rad/s
    omega_l = c0/w_laser * 2*np.pi
    omega0 = c0/w_atom * 2*np.pi
    intensity = 2*power/(np.pi*waist**2)
    acshift = 3*np.pi*c0**2/(2*omega0**3) * (lw/(omega0-omega_l)+\
                                             lw/(omega0+omega_l)) * intensity

    return acshift


def trapfreqs(U0, waist, mass, w_laser):
    """Trap frequencies for a single beam ODT

    **Inputs**

      * U0: float, trap depth of the ODT in Joules
      * waist: float, waist (1/e^2 radius) of the beam in meters
      * mass: float, mass of the atom
      * w_laser: float, laser wavelength in meters

    **Outputs**

      * wr: float, radial trap frequency in rad/s
      * wz: float, axial trap frequency in rad/s

    """

    zR = np.pi*waist**2/w_laser
    wr = np.sqrt(4*U0/(mass*waist**2))
    wz = np.sqrt(2*U0/(mass*zR**2))

    return wr, wz


def saturation_intensity(w_atom, linewidth):
    """The saturation intensity

    **Inputs**

      * w_atom: float, resonant wavelength for the atom. For very large
                detuning, this is the middle between the D1 and D2 lines.
      * linewidth: float, linewidth for the atomic transition (usually the one
                   for the D2 line if an alkali atom) in Hz (not rad/s!)

    **Outputs**

      * Isat: float, the saturation intensity in W/m^2

    """

    lw = linewidth * 2*np.pi
    Isat = (np.pi*h*c0*lw) / (3*w_atom**3)
    return Isat


def scattering_rate(w_laser, w_atom, power, waist, linewidth):
    """Scattering rate per atom

    **Inputs**

      * w_laser: float, laser wavelength in meters
      * w_atom: float, resonant wavelength for the atom. For very large
                detuning, this is the middle between the D1 and D2 lines.
      * power: float, laser power in Watts
      * waist: float, waist size (i.e. 1/e^2 radius) of the laser beam in meters
      * linewidth: float, linewidth for the atomic transition (usually the one
                   for the D2 line if an alkali atom) in Hz (not rad/s!)

    **Outputs**

      * scrate: float, the scattering rate in Hz

    **Notes**



    """

    lw = linewidth*2*np.pi # to rad/s
    omega_l = c0/w_laser * 2*np.pi
    omega0 = c0/w_atom * 2*np.pi
    intensity = 2*power/(np.pi*waist**2)
    s0 = intensity / saturation_intensity(w_atom, lw)

    detuning_NoRWA = 1/(lw/(omega0-omega_l) + lw/(omega0+omega_l))
    scrate_metcalf = (s0 * lw/2) / (1 + s0 + 4*detuning_NoRWA**2)

    # Grimm review paper
    scrate_grimm = 3*np.pi*c0**2/(2*hbar*omega0**3) * (omega_l/omega0)**3 * \
                 (lw/(omega0-omega_l) + lw/(omega0+omega_l))**2 * intensity

    detuning = (omega0-omega_l)
    rabi = lw * np.sqrt(s0/2)
    scrate_foot = lw/2 * (0.5*rabi**2) / (detuning**2 + 0.5*rabi**2 + 0.25*lw**2)\
                * (1+(omega0-omega_l)/(omega0+omega_l))**2

    # Cohen-Tannoudji, Photons & Atoms, Intro to QED, p.77
    dWdt = 1./3 * e0**2/(4*np.pi*eps0) * e0**2 * (2*intensity/(c0*eps0))\
         /me**2 * omega_l**4/c0**3 / ((omega0**2 - omega_l**2)**2 + \
                                        lw**2*omega_l**6/omega0**4)
    scrate_ct = dWdt / (hbar * omega_l)

    scrate_ralf = scrate_metcalf * (omega_l/omega0)**3
    return scrate_ralf, scrate_metcalf, scrate_grimm, scrate_foot, scrate_ct
