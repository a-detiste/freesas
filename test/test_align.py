#!/usr/bin/python
__author__ = "Guillaume"
__license__ = "MIT"
__copyright__ = "2015, ESRF" 

import numpy
import unittest
import sys, os
from utilstests import base, join
from freesas.model import SASModel
from freesas.align import alignment
from freesas.transformations import translation_matrix, euler_matrix
from scipy.optimize import fmin

def move(model):
    """
    random movement of the molecule
    
    Parameters
    ----------
    model: SASModel
    
    Output
    ----------
    mol: 2D array, coordinates of the molecule after a translation and a rotation
    """
    mol = model.atoms
    
    vect = numpy.random.random(3)
    translation = translation_matrix(vect)
    
    euler = numpy.random.random(3)
    rotation = euler_matrix(euler[0], euler[1], euler[2])
    
    mol = numpy.dot(rotation, mol.T)
    mol = numpy.dot(translation, mol).T
    
    return mol

def assign_random_mol(inf=None, sup=None):
    if not inf: inf = 0
    if not sup: sup = 100
    molecule = numpy.random.randint(inf ,sup, size=400).reshape(100,4).astype(float)
    molecule[:,-1] = 1.0
    m = SASModel(molecule)
    return m

class TestAlign(unittest.TestCase):
    testfile1 = join(base, "testdata", "dammif-01.pdb")
    testfile2 = join(base, "testdata", "dammif-02.pdb")
    
    def test_alignment(self):
        m = assign_random_mol()
        n = SASModel(m.atoms)
        n.atoms = move(n)
        m.canonical_parameters()
        n.canonical_parameters()
        param1 = m.can_param
        param2 = n.can_param
        mol1_can = m.transform(param1,[1,1,1])
        mol2_can = n.transform(param2,[1,1,1])
        assert m.dist(n, mol1_can, mol2_can) != 0, "pb of movement"
        sym2 = alignment(m,n)
        mol2_align = n.transform(param2, sym2)
        dist = m.dist(n, mol1_can, mol2_align)
        self.assertAlmostEqual(dist, 0, 12, "bad alignment %s!=0"%(dist))

    def test_usefull_alignment(self):
        m = assign_random_mol()
        n = assign_random_mol()
        m.canonical_parameters()
        n.canonical_parameters()
        mol1_can = m.transform(m.can_param,[1,1,1])
        mol2_can = n.transform(n.can_param,[1,1,1])
        dist_before = m.dist(n, mol1_can, mol2_can)
        symmetry = alignment(m,n)
        mol2_sym = n.transform(n.can_param, symmetry)
        dist_after = m.dist(n, mol1_can, mol2_sym)
        self.assertGreaterEqual(dist_before, dist_after, "increase of distance after alignment %s<%s"%(dist_before, dist_after))

    def test_optimisation_align(self):
        m = assign_random_mol()
        n = assign_random_mol()
        m.canonical_parameters()
        n.canonical_parameters()
        p0 = n.can_param
        sym = alignment(m,n)
        dist_before = m.dist_after_movement(p0, n, sym)
        p = fmin(m.dist_after_movement, p0, args=(n, sym), maxiter=200)
        dist_after = m.dist_after_movement(p, n, sym)
        self.assertGreater(dist_before, dist_after, msg="distance is not optimised : %s<=%s"%(dist_before,dist_after))

def test_suite_all_alignment():
    testSuite = unittest.TestSuite()
    testSuite.addTest(TestAlign("test_alignment"))
    testSuite.addTest(TestAlign("test_usefull_alignment"))
    testSuite.addTest(TestAlign("test_optimisation_align"))
    return testSuite

if __name__ == '__main__':
    mysuite = test_suite_all_alignment()
    runner = unittest.TextTestRunner()
    runner.run(mysuite)