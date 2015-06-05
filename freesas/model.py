__author__ = "Guillaume"
__license__ = "MIT"
__copyright__ = "2015, ESRF"

import numpy
import threading
try:
    from . import _distance
except ImportError:
    _distance = None
from . import transformations

def delta_expand(vec1, vec2):
    """
    @param vec1, vec2: 1d-array
    @return: difference v1-v2 for any element of v1 and v2 (i.e a 2D array)
    """
    v1 = numpy.ascontiguousarray(vec1)
    v2 = numpy.ascontiguousarray(vec2)
    v1.shape = -1,1
    v2.shape = 1,-1
    v1.strides = v1.strides[0],0
    v2.strides = 0,v2.strides[-1]
    return v1-v2


class SASModel:
    def __init__(self, molecule=None):
        self.atoms =  molecule if molecule is not None else []# initial coordinates of each dummy atoms of the molecule, fourth column full of one for the transformation matrix
        self.radius = 1.0
        self.header = "" # header of the PDB file
        self.com = []
        self._fineness = None
        self.inertensor = []
        self.can_param = []
        self.enantiomer = None#symmetry used on the molecule
        self._sem = threading.Semaphore()

    def __repr__(self):
        return "SAS model with %i atoms"%len(self.atoms)

    def read(self, filename):
        """
        read the PDB file
        extract coordinates of each dummy atom
        """
        header = []
        atoms = []
        for line in open(filename):
            if line.startswith("ATOM"):
                args = line.split()
                x = float(args[6])
                y = float(args[7])
                z = float(args[8])
                atoms.append([x, y, z])
            header.append(line)
        self.header = header
        atom3 = numpy.array(atoms)
        self.atoms = numpy.append(atom3, numpy.ones((atom3.shape[0],1),dtype="float"), axis=1)

    def save(self, filename):
        """
        save the position of each dummy atom in a PDB file
        """
        nr = 0
        self.atoms = numpy.delete(self.atoms, 3, 1)
        with open(filename, "w") as pdbout:
            for line in self.header:
                if line.startswith("ATOM"):
                    if nr<self.atoms.shape[0]:
                        line = line[:30]+"%8.3f%8.3f%8.3f"%tuple(self.atoms[nr])+line[54:]
                    else:
                        line = ""
                    nr += 1
                pdbout.write(line)

    def centroid(self):
        """
        Calculate the position of the center of mass of the molecule
        @return self.com: 1d array, coordinates of the center of mass of the molecule
        """
        mol = self.atoms[:,0:3]
        self.com = mol.mean(axis=0)
        return self.com

    def inertiatensor(self):
        """
        calculate the inertia tensor of the protein
        @return self.inertensor: inertia tensor of the molecule
        """
        if len(self.com)==0:
            self.com = self.centroid()
        
        mol = self.atoms[:,0:3] - self.com
        self.inertensor = numpy.empty((3, 3), dtype = "float")
        delta_kron = lambda i, j : 1 if i==j else 0
        for i in range(3):
            for j in range(i,3):
                self.inertensor[i,j]= self.inertensor[j,i] = (delta_kron(i,j)*(mol**2).sum(axis=1) - (mol[:,i]*mol[:,j])).sum()/mol.shape[0]
        return self.inertensor

    def canonical_translate(self):
        """
        Calculate the translation matrix to translate the center of mass of the molecule on the origin of the base
        @return trans: translation matrix 
        """
        if len(self.com)==0:
            self.com = self.centroid()
        
        trans = numpy.identity(4, dtype = "float")
        trans[0:3,3] = -self.com
        return trans

    def canonical_rotate(self):
        """
        Calculate the rotation matrix to align inertia momentum of the molecule on principal axis.
        @return rot: rotation matrix det==1
        """
        if len(self.inertensor)==0:
            self.inertensor = self.inertiatensor()
        
        w, v = numpy.linalg.eigh(self.inertensor)
        mat = v[:, w.argsort()]
        
        rot = numpy.zeros((4,4), dtype="float")
        rot[3,3] = 1
        rot[:3,:3] = mat.T
        
        det = numpy.linalg.det(mat)     
        if det>0:
            self.enantiomer = [1,1,1]
        else:
            self.enantiomer = [-1,-1,-1]
            mirror = numpy.array([[-1,0,0,0],[0,-1,0,0],[0,0,-1,0],[0,0,0,1]], dtype="float")
            rot = numpy.dot(mirror, rot)
        
        return rot

    def canonical_parameters(self):
        """
        Save the 6 canonical parameters of the initial molecule:
        x0, y0, z0, the position of the center of mass
        phi, theta, psi, the three Euler angles of the canonical rotation (axis:x,y',z'')
        """
        rot = self.canonical_rotate()
        trans = self.canonical_translate()
        
        assert numpy.linalg.det(rot)>0, "determinant of rotation matrix is negative"
        
        angles = transformations.euler_from_matrix(rot)
        shift = transformations.translation_from_matrix(trans)
        self.can_param = [shift[0], shift[1], shift[2], angles[0], angles[1], angles[2]]

    def _calc_fineness(self, use_cython=True):
        """
        Calculate the fineness of the structure, i.e the average distance between the neighboring points in the model
        """
        if _distance and use_cython:
            return _distance.calc_fineness(self.atoms)

        else:
            D = delta_expand(self.atoms[:,0], self.atoms[:,0])**2+delta_expand(self.atoms[:,1], self.atoms[:,1])**2+delta_expand(self.atoms[:,2], self.atoms[:,2])**2
            d12 = (D.max()*numpy.eye(self.atoms[:,0].size)+D).min(axis=0).mean()
            fineness = numpy.sqrt(d12)
            return fineness

    @property
    def fineness(self):
        if self._fineness is None:
            with self._sem:
                if self._fineness is None:
                    self._fineness = self._calc_fineness()
        return self._fineness

    def dist(self, other, molecule1, molecule2, use_cython=True):
        """
        Calculate the distance with another model
        @param self,other: two SASModel
        @param molecule1: 2d array of the position of each atom of the first molecule
        @param molecule2: 2d array of the position of each atom of the second molecule
        @return D: NSD between the 2 molecules, in their position molecule1 and molecule2
        """
        if _distance and use_cython:
            return _distance.calc_distance(molecule1, molecule2, self.fineness, other.fineness)
        
        else:
            mol1 = molecule1[:,0:3]
            mol2 = molecule2[:,0:3]

            mol1x = mol1[:,0]
            mol1y = mol1[:,1]
            mol1z = mol1[:,2]
            mol1x.shape = mol1.shape[0],1
            mol1y.shape = mol1.shape[0],1
            mol1z.shape = mol1.shape[0],1

            mol2x = mol2[:,0]
            mol2y = mol2[:,1]
            mol2z = mol2[:,2]
            mol2x.shape = mol2.shape[0],1
            mol2y.shape = mol2.shape[0],1
            mol2z.shape = mol2.shape[0],1

            d2=delta_expand(mol1x,mol2x)**2+delta_expand(mol1y,mol2y)**2+delta_expand(mol1z,mol2z)**2

            D = (0.5*((1./((mol1.shape[0])*other.fineness*other.fineness))*(d2.min(axis=1).sum())+(1./((mol2.shape[0])*self.fineness*self.fineness))*(d2.min(axis=0)).sum()))**0.5
            return D

    def transform(self, param, symmetry):
        """
        Calculate the new coordinates of each dummy atoms of the molecule after a transformation defined by six parameters and a symmetry
        
        @param param: 6 parameters of transformation (3 coordinates of translation, 3 Euler angles)
        @param symmetry: list of three constants which define a symmetry to apply
        @return mol: 2d array, coordinates after transformation
        """
        mol = self.atoms
        
        vect = numpy.array([param[0:3]])
        angles = (param[3:6])
        sym = numpy.array([[symmetry[0],0,0,0], [0,symmetry[1],0,0], [0,0,symmetry[2],0], [0,0,0,1]], dtype="float")
        
        translat1 = transformations.translation_matrix(vect)
        rotation = transformations.euler_matrix(*angles)
        translat2 = numpy.dot(numpy.dot(rotation, translat1),rotation.T)
        transformation = numpy.dot(translat2, rotation)
        
        mol = numpy.dot(transformation, mol.T)
        mol = numpy.dot(sym, mol).T
        return mol

    def dist_after_movement(self, param, other, symmetry):
        """
        The first molecule, molref, is put on its canonical position.
        The second one, mol2, is moved following the transformation selected
        
        @param param: list of 6 parameters for the transformation, 3 coordinates of translation and 3 Euler angles
        @param symmetry: list of three constants which define a symmetry to apply
        @return distance: the NSD between the first molecule and the second one after its movement
        """
        if not self.can_param:
            self.canonical_parameters()
        
        can_param1 = self.can_param
        molref_can = self.transform(can_param1, [1,1,1])#molecule reference put on its canonical position
        
        mol2_moved = other.transform(param, symmetry)#movement selected applied to mol2
        distance = self.dist(other, molref_can, mol2_moved)
        
        return distance