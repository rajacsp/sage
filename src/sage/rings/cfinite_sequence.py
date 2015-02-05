# -*- coding: utf-8 -*-
r"""
C-Finite Sequences

C-finite infinite sequences satisfy homogenous linear recurrences with constant coefficients:

.. MATH::

    a_{n+d} = c_0a_n + c_1a_{n+1} + \cdots + c_{d-1}a_{n+d-1}, \quad d>0.

CFiniteSequences are completely defined by their ordinary generating function (o.g.f., which
is always a :mod:`fraction <sage.rings.fraction_field_element>` of
:mod:`polynomials <sage.rings.polynomial.polynomial_element>` over `\mathbb{Z}` or `\mathbb{Q}` ).

EXAMPLES::

    sage: R.<x> = QQ[]
    sage: fibo = CFiniteSequence(x/(1-x-x^2))        # the Fibonacci sequence
    sage: fibo
    C-finite sequence, generated by x/(-x^2 - x + 1)
    sage: fibo.parent()
    Fraction Field of Univariate Polynomial Ring in x over Rational Field
    sage: fibo.parent().category()
    Category of quotient fields

Finite subsets of the sequence are accessible via python slices::

    sage: fibo[137]                 #the 137th term of the Fibonacci sequence
    19134702400093278081449423917
    sage: fibo[137] == fibonacci(137)
    True
    sage: fibo[0:12]
    [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89]
    sage: fibo[14:4:-2]
    [377, 144, 55, 21, 8]

They can be created also from the coefficients and start values of a recurrence::

    sage: r = CFiniteSequence.from_recurrence([1,1],[0,1])
    sage: r == fibo
    True

Given enough values, the o.g.f. of a C-finite sequence
can be guessed::

    sage: r = CFiniteSequence.guess([0,1,1,2,3,5,8])
    sage: r == fibo
    True

.. SEEALSO::

    :func:`fibonacci`, :class:`BinaryRecurrenceSequence`

AUTHORS:

- Ralf Stephan (2014): initial version

REFERENCES:

.. [GK82] Greene, Daniel H.; Knuth, Donald E. (1982), "2.1.1 Constant
   coefficients - A) Homogeneous equations", Mathematics for the Analysis
   of Algorithms (2nd ed.), Birkhäuser, p. 17.
.. [SZ94] Bruno Salvy and Paul Zimmermann. - Gfun: a Maple package for
   the manipulation of generating and holonomic functions in one variable.
   - Acm transactions on mathematical software, 20.2:163-177, 1994.
.. [Z11] Zeilberger, Doron. "The C-finite ansatz." The Ramanujan Journal
   (2011): 1-10.
"""
#*****************************************************************************
#       Copyright (C) 2014 Ralf Stephan <gtrwst9@gmail.com>,
#
#  Distributed under the terms of the GNU General Public License (GPL) v2.0
#
#    This code is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    General Public License for more details.
#
#  The full text of the GPL is available at:
#
#                  http://www.gnu.org/licenses/gpl-2.0.html
#*****************************************************************************

from sage.rings.integer import Integer
from sage.rings.integer_ring import ZZ
from sage.rings.rational_field import QQ
from sage.rings.arith import gcd
from sage.rings.polynomial.polynomial_ring_constructor import PolynomialRing
from sage.rings.laurent_series_ring import LaurentSeriesRing
from sage.rings.power_series_ring import PowerSeriesRing
from sage.rings.fraction_field_element import FractionFieldElement

from sage.interfaces.gp import Gp
from sage.misc.all import sage_eval

_gp = None


class CFiniteSequence(FractionFieldElement):

    def __init__(self, ogf, *args, **kwargs):
        """
        Create a C-finite sequence given its ordinary generating function.

        INPUT:

        - ``ogf`` -- the ordinary generating function, a fraction of polynomials over the rationals

        OUTPUT:

        - A CFiniteSequence object

        EXAMPLES::

            sage: R.<x> = QQ[]
            sage: CFiniteSequence((2-x)/(1-x-x^2))     # the Lucas sequence
            C-finite sequence, generated by (-x + 2)/(-x^2 - x + 1)
            sage: CFiniteSequence(x/(1-x)^3)           # triangular numbers
            C-finite sequence, generated by x/(-x^3 + 3*x^2 - 3*x + 1)

        Polynomials are interpreted as finite sequences, or recurrences of degree 0::

            sage: CFiniteSequence(x^2-4*x^5)
            Finite sequence [1, 0, 0, -4], offset = 2
            sage: CFiniteSequence(1)
            Finite sequence [1], offset = 0

        This implementation allows any polynomial fraction as o.g.f. by interpreting
        any power of `x` dividing the o.g.f. numerator or denominator as a right or left shift
        of the sequence offset::

            sage: CFiniteSequence(x^2+3/x)
            Finite sequence [3, 0, 0, 1], offset = -1
            sage: CFiniteSequence(1/x+4/x^3)
            Finite sequence [4, 0, 1], offset = -3
            sage: P = LaurentPolynomialRing(QQ.fraction_field(), 'X')
            sage: X=P.gen()
            sage: CFiniteSequence(1/(1-X))
            C-finite sequence, generated by 1/(-x + 1)

        The o.g.f. is always normalized to get a denominator constant coefficient of `+1`::

            sage: CFiniteSequence(1/(x-2))
            C-finite sequence, generated by -1/2/(-1/2*x + 1)

        TESTS::

            sage: P.<x> = QQ[]
            sage: CFiniteSequence(0.1/(1-x))
            Traceback (most recent call last):
            ...
            ValueError: O.g.f. base not rational.
            sage: P.<x,y> = QQ[]
            sage: CFiniteSequence(x*y)
            Traceback (most recent call last):
            ...
            NotImplementedError: Multidimensional o.g.f. not implemented.
        """
        br = ogf.base_ring()
        if not(br in (QQ, ZZ)):
            raise ValueError('O.g.f. base not rational.')

        P = PolynomialRing(QQ, 'x')
        if ogf in QQ:
            ogf = P(ogf)
        if hasattr(ogf, 'numerator'):
            try:
                num = P(ogf.numerator())
                den = P(ogf.denominator())
            except TypeError:
                if ogf.numerator().parent().ngens() > 1:
                    raise NotImplementedError('Multidimensional o.g.f. not implemented.')
                else:
                    raise ValueError('Numerator and denominator must be polynomials.')
        else:
            num = P(ogf)
            den = 1

        # Transform the ogf numerator and denominator to canonical form
        # to get the correct offset, degree, and recurrence coeffs and
        # start values.
        self._off = 0
        self._deg = 0
        if isinstance(ogf, FractionFieldElement) and den == 1:
            ogf = num        # case p(x)/1: fall through

        if isinstance(ogf, FractionFieldElement):
            x = P.gen()
            if num.constant_coefficient() == 0:
                self._off = num.valuation()
                num = P(num / x ** self._off)
            elif den.constant_coefficient() == 0:
                self._off = -den.valuation()
                den = P(den * x ** self._off)
            f = den.constant_coefficient()
            num = P(num / f)
            den = P(den / f)
            f = gcd(num, den)
            num = P(num / f)
            den = P(den / f)
            self._deg = den.degree()
            self._c = [-den.list()[i] for i in range(1, self._deg + 1)]
            if self._off >= 0:
                num = x ** self._off * num
            else:
                den = x ** (-self._off) * den

            # determine start values (may be different from _get_item_ values)
            alen = max(self._deg, num.degree() + 1)
            R = LaurentSeriesRing(QQ, 'x', default_prec=alen)
            rem = num % den
            if den != 1:
                self._a = R(num / den).list()
                self._aa = R(rem / den).list()[:self._deg]  # needed for _get_item_
            else:
                self._a = num.list()
            if len(self._a) < alen:
                self._a.extend([0] * (alen - len(self._a)))

            super(CFiniteSequence, self).__init__(P.fraction_field(), num, den, *args, **kwargs)

        elif ogf.parent().is_integral_domain():
            super(CFiniteSequence, self).__init__(ogf.parent().fraction_field(), P(ogf), 1, *args, **kwargs)
            self._c = []
            self._off = P(ogf).valuation()
            if ogf == 0:
                self._a = [0]
            else:
                self._a = ogf.parent()((ogf / (ogf.parent().gen()) ** self._off)).list()
        else:
            raise ValueError("Cannot convert a " + str(type(ogf)) + " to CFiniteSequence.")

    @classmethod
    def from_recurrence(cls, coefficients, values):
        """
        Create a C-finite sequence given the coefficients $c$ and
        starting values $a$ of a homogenous linear recurrence.

        .. MATH::

            a_{n+d} = c_0a_n + c_1a_{n+1} + \cdots + c_{d-1}a_{n+d-1}, \quad d\ge0.

        INPUT:

        - ``coefficients`` -- a list of rationals

        - ``values`` -- start values, a list of rationals

        OUTPUT:

        - A CFiniteSequence object

        EXAMPLES::

            sage: R.<x> = QQ[]
            sage: CFiniteSequence.from_recurrence([1,1],[0,1])   # Fibonacci numbers
            C-finite sequence, generated by x/(-x^2 - x + 1)
            sage: CFiniteSequence.from_recurrence([-1,2],[0,1])    # natural numbers
            C-finite sequence, generated by x/(x^2 - 2*x + 1)
            sage: r = CFiniteSequence.from_recurrence([-1],[1])
            sage: s = CFiniteSequence.from_recurrence([-1],[1,-1])
            sage: r == s
            True
            sage: r = CFiniteSequence(x^3/(1-x-x^2))
            sage: s = CFiniteSequence.from_recurrence([1,1],[0,0,0,1,1])
            sage: r == s
            True
            sage: CFiniteSequence.from_recurrence(1,1)
            Traceback (most recent call last):
            ...
            ValueError: Wrong type for recurrence coefficient list.
        """
        if not isinstance(coefficients, list):
            raise ValueError("Wrong type for recurrence coefficient list.")
        if not isinstance(values, list):
            raise ValueError("Wrong type for recurrence start value list.")
        deg = len(coefficients)

        co = coefficients[::-1]
        co.extend([0] * (len(values) - deg))
        R = PolynomialRing(QQ, 'x')
        x = R.gen()
        den = -1 + sum([x ** (n + 1) * co[n] for n in range(deg)])
        num = -values[0] + sum([x ** n * (-values[n]
                                          + sum([values[k] * co[n - 1 - k]
                                                 for k in range(n)]))
                                for n in range(1, len(values))])
        return cls(num / den)

    def __repr__(self):
        """
        Return textual definition of sequence.

        TESTS::

            sage: R.<x> = QQ[]
            sage: CFiniteSequence(1/x^5)
            Finite sequence [1], offset = -5
            sage: CFiniteSequence(x^3)
            Finite sequence [1], offset = 3
        """
        if self._deg == 0:
            if self.ogf() == 0:
                return 'Constant infinite sequence 0.'
            else:
                return 'Finite sequence ' + str(self._a) + ', offset = ' + str(self._off)
        else:
            return 'C-finite sequence, generated by ' + str(self.ogf())

    def _add_(self, other):
        """
        Addition of C-finite sequences.

        TESTS::

            sage: R.<x> = QQ[]
            sage: r = CFiniteSequence(1/(1-2*x))
            sage: r[0:5]                  # a(n) = 2^n
            [1, 2, 4, 8, 16]
            sage: s = CFiniteSequence.from_recurrence([1],[1])
            sage: (r + s)[0:5]            # a(n) = 2^n + 1
            [2, 3, 5, 9, 17]
            sage: r + 0 == r
            True
            sage: (r + x^2)[0:5]
            [1, 2, 5, 8, 16]
            sage: (r + 3/x)[-1]
            3
            sage: r = CFiniteSequence(x)
            sage: r + 0 == r
            True
            sage: CFiniteSequence(0) + CFiniteSequence(0)
            Constant infinite sequence 0.
        """
        return CFiniteSequence(self.ogf() + other.numerator() / other.denominator())

    def _sub_(self, other):
        """
        Subtraction of C-finite sequences.

        TESTS::

            sage: R.<x> = QQ[]
            sage: r = CFiniteSequence(1/(1-2*x))
            sage: r[0:5]                  # a(n) = 2^n
            [1, 2, 4, 8, 16]
            sage: s = CFiniteSequence.from_recurrence([1],[1])
            sage: (r - s)[0:5]            # a(n) = 2^n + 1
            [0, 1, 3, 7, 15]
        """
        return CFiniteSequence(self.ogf() - other.numerator() / other.denominator())

    def _mul_(self, other):
        """
        Multiplication of C-finite sequences.

        TESTS::

            sage: r = CFiniteSequence.guess([1,2,3,4,5,6])
            sage: (r*r)[0:6]                  # self-convolution
            [1, 4, 10, 20, 35, 56]
            sage: R.<x>=QQ[]
            sage: r = CFiniteSequence(x)
            sage: r*1 == r
            True
            sage: r*-1
            Finite sequence [-1], offset = 1
            sage: CFiniteSequence(0) * CFiniteSequence(1)
            Constant infinite sequence 0.
        """
        return CFiniteSequence(self.ogf() * other.numerator() / other.denominator())

    def _div_(self, other):
        """
        Division of C-finite sequences.

        TESTS::

            sage: r = CFiniteSequence.guess([1,2,3,4,5,6])
            sage: (r/2)[0:6]
            [1/2, 1, 3/2, 2, 5/2, 3]
            sage: R.<x> = PolynomialRing(QQ, 'x')
            sage: s = CFiniteSequence(x)
            sage: s/(s*-1 + 1)
            C-finite sequence, generated by x/(-x + 1)
        """
        return CFiniteSequence(self.ogf() / (other.numerator() / other.denominator()))

    def coefficients(self):
        """
        Return the coefficients of the recurrence representation of the
        C-finite sequence.

        OUTPUT:

        - A list of values

        EXAMPLES::

            sage: R.<x>=QQ[]
            sage: lucas = CFiniteSequence((2-x)/(1-x-x^2))   # the Lucas sequence
            sage: lucas.coefficients()
            [1, 1]
        """
        return self._c

    def __eq__(self, other):
        """
        Compare two CFiniteSequences.

        EXAMPLES::

            sage: r = CFiniteSequence.from_recurrence([1,1],[2,1])
            sage: s = CFiniteSequence.from_recurrence([-1],[1])
            sage: r == s
            False
            sage: R.<x> = QQ[]
            sage: r = CFiniteSequence.from_recurrence([-1],[1])
            sage: s = CFiniteSequence(1/(1+x))
            sage: r == s
            True
        """
        return self.ogf() == other.ogf()

    def __getitem__(self, key):
        r"""
        Return a slice of the sequence.

        EXAMPLE::

            sage: r = CFiniteSequence.from_recurrence([3,3],[2,1])
            sage: r[2]
            9
            sage: r[101]
            16158686318788579168659644539538474790082623100896663971001
            sage: R.<x> = QQ[]
            sage: r = CFiniteSequence(1/(1-x))
            sage: r[5]
            1
            sage: r = CFiniteSequence(x)
            sage: r[0]
            0
            sage: r[1]
            1
            sage: r = CFiniteSequence(R(0))
            sage: r[66]
            0
            sage: lucas = CFiniteSequence.from_recurrence([1,1],[2,1])
            sage: lucas[5:10]
            [11, 18, 29, 47, 76]
            sage: r = CFiniteSequence((2-x)/x/(1-x-x*x))
            sage: r[0:4]
            [1, 3, 4, 7]
            sage: r = CFiniteSequence(1-2*x^2)
            sage: r[0:4]
            [1, 0, -2, 0]
            sage: r[-1:4]             # not tested, python will not allow this!
            [0, 1, 0 -2, 0]
            sage: r = CFiniteSequence((-2*x^3 + x^2 + 1)/(-2*x + 1))
            sage: r[0:5]              # handle ogf > 1
            [1, 2, 5, 8, 16]
            sage: r[-2]
            0
            sage: r = CFiniteSequence((-2*x^3 + x^2 - x + 1)/(2*x^2 - 3*x + 1))
            sage: r[0:5]
            [1, 2, 5, 9, 17]
            sage: s=CFiniteSequence((1-x)/(-x^2 - x + 1))
            sage: s[0:5]
            [1, 0, 1, 1, 2]
            sage: s=CFiniteSequence((1+x^20+x^40)/(1-x^12)/(1-x^30))
            sage: s[0:20]
            [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0]
            sage: s=CFiniteSequence(1/((1-x^2)*(1-x^6)*(1-x^8)*(1-x^12)))
            sage: s[999998]
            289362268629630
        """
        if isinstance(key, slice):
            m = max(key.start, key.stop)
            return [self[ii] for ii in xrange(*key.indices(m + 1))]
        elif isinstance(key, (int, Integer)):
            from sage.matrix.constructor import Matrix
            d = self._deg
            if (self._off <= key and key < self._off + len(self._a)):
                return self._a[key - self._off]
            elif d == 0:
                return 0
            (quo, rem) = self.numerator().quo_rem(self.denominator())
            wp = quo[key - self._off]
            if key < self._off:
                return wp
            A = Matrix(QQ, 1, d, self._c)
            B = Matrix.identity(QQ, d - 1)
            C = Matrix(QQ, d - 1, 1, 0)
            if quo == 0:
                V = Matrix(QQ, d, 1, self._a[:d][::-1])
            else:
                V = Matrix(QQ, d, 1, self._aa[:d][::-1])
            M = Matrix.block([[A], [B, C]], subdivide=False)

            return wp + list(M ** (key - self._off) * V)[d - 1][0]
        else:
            raise TypeError("invalid argument type")

    def ogf(self):
        """
        Return the ordinary generating function associated with
        the CFiniteSequence.

        This is always a fraction of polynomials in the base ring.

        EXAMPLES::

            sage: r = CFiniteSequence.from_recurrence([2],[1])
            sage: r.ogf()
            1/(-2*x + 1)
            sage: CFiniteSequence(0).ogf()
            0
        """
        if self.numerator() == 0:
            return 0
        return self.numerator() / self.denominator()

    def recurrence_repr(self):
        """
        Return a string with the recurrence representation of
        the C-finite sequence.

        OUTPUT:

        - A CFiniteSequence object

        EXAMPLES::

            sage: R.<x> = QQ[]
            sage: CFiniteSequence((2-x)/(1-x-x^2)).recurrence_repr()
            'Homogenous linear recurrence with constant coefficients of degree 2: a(n+2) = a(n+1) + a(n), starting a(0...) = [2, 1]'
            sage: CFiniteSequence(x/(1-x)^3).recurrence_repr()
            'Homogenous linear recurrence with constant coefficients of degree 3: a(n+3) = 3*a(n+2) - 3*a(n+1) + a(n), starting a(1...) = [1, 3, 6]'
            sage: CFiniteSequence(1).recurrence_repr()
            'Finite sequence [1], offset 0'
            sage: r = CFiniteSequence((-2*x^3 + x^2 - x + 1)/(2*x^2 - 3*x + 1))
            sage: r.recurrence_repr()
            'Homogenous linear recurrence with constant coefficients of degree 2: a(n+2) = 3*a(n+1) - 2*a(n), starting a(0...) = [1, 2, 5, 9]'
            sage: r = CFiniteSequence(x^3/(1-x-x^2))
            sage: r.recurrence_repr()
            'Homogenous linear recurrence with constant coefficients of degree 2: a(n+2) = a(n+1) + a(n), starting a(3...) = [1, 1, 2, 3]'
        """
        if self._deg == 0:
            return 'Finite sequence %s, offset %d' % (str(self._a), self._off)
        else:
            if self._c[0] == 1:
                cstr = 'a(n+%d) = a(n+%d)' % (self._deg, self._deg - 1)
            elif self._c[0] == -1:
                cstr = 'a(n+%d) = -a(n+%d)' % (self._deg, self._deg - 1)
            else:
                cstr = 'a(n+%d) = %s*a(n+%d)' % (self._deg, str(self._c[0]), self._deg - 1)
            for i in range(1, self._deg):
                j = self._deg - i - 1
                if self._c[i] < 0:
                    if self._c[i] == -1:
                        cstr = cstr + ' - a(n+%d)' % (j,)
                    else:
                        cstr = cstr + ' - %d*a(n+%d)' % (-(self._c[i]), j)
                elif self._c[i] > 0:
                    if self._c[i] == 1:
                        cstr = cstr + ' + a(n+%d)' % (j,)
                    else:
                        cstr = cstr + ' + %d*a(n+%d)' % (self._c[i], j)
            cstr = cstr.replace('+0', '')
        astr = ', starting a(%s...) = [' % str(self._off)
        maxwexp = self.numerator().quo_rem(self.denominator())[0].degree() + 1
        for i in range(maxwexp + self._deg):
            astr = astr + str(self.__getitem__(self._off + i)) + ', '
        astr = astr[:-2] + ']'
        return 'Homogenous linear recurrence with constant coefficients of degree ' + str(self._deg) + ': ' + cstr + astr

    def series(self, n):
        """
        Return the Laurent power series associated with the
        CFiniteSequence, with precision `n`.

        INPUT:

        - `n` -- a nonnegative integer

        EXAMPLES::

            sage: r = CFiniteSequence.from_recurrence([-1,2],[0,1])
            sage: s = r.series(4); s
            x + 2*x^2 + 3*x^3 + 4*x^4 + O(x^5)
            sage: type(s)
            <type 'sage.rings.laurent_series_ring_element.LaurentSeries'>
        """
        R = LaurentSeriesRing(QQ, 'x', default_prec=n)
        return R(self.ogf())

    @staticmethod
    def guess(sequence, algorithm='sage'):
        """
        Return the minimal CFiniteSequence that generates the sequence.

        Assume the first value has index 0.

        INPUT:

        - ``sequence`` -- list of integers

        - ``algorithm`` -- string
            - 'sage' - the default is to use Sage's matrix kernel function
            - 'pari' - use Pari's implementation of LLL
            - 'bm' - use Sage's Berlekamp-Massey algorithm

        OUTPUT:

        - a CFiniteSequence, or 0 if none could be found

        EXAMPLES::

            sage: CFiniteSequence.guess([1,2,4,8,16,32])
            C-finite sequence, generated by 1/(-2*x + 1)
            sage: r = CFiniteSequence.guess([1,2,3,4,5])
            Traceback (most recent call last):
            ...
            ValueError: Sequence too short for guessing.

        With the default kernel method and Pari LLL, all values are taken
        into account, and if no o.g.f. can be found, `0` is returned::

            sage: CFiniteSequence.guess([1,0,0,0,0,1])
            0

        With Berlekamp-Massey, if an odd number of values is given, the last one is dropped.
        So with an odd number of values the result may not generate the last value::

            sage: r = CFiniteSequence.guess([1,2,4,8,9], algorithm='bm'); r
            C-finite sequence, generated by 1/(-2*x + 1)
            sage: r[0:5]
            [1, 2, 4, 8, 16]
        """
        S = PolynomialRing(QQ, 'x')
        if algorithm == 'bm':
            from sage.matrix.berlekamp_massey import berlekamp_massey
            if len(sequence) < 2:
                raise ValueError('Sequence too short for guessing.')
            R = PowerSeriesRing(QQ, 'x')
            if len(sequence) % 2 == 1:
                sequence = sequence[:-1]
            l = len(sequence) - 1
            denominator = S(berlekamp_massey(sequence).list()[::-1])
            numerator = R(S(sequence) * denominator, prec=l).truncate()

            return CFiniteSequence(numerator / denominator)
        elif algorithm == 'pari':
            global _gp
            if len(sequence) < 6:
                raise ValueError('Sequence too short for guessing.')
            if _gp is None:
                _gp = Gp()
                _gp("ggf(v)=local(l,m,p,q,B);l=length(v);B=floor(l/2);\
                if(B<3,return(0));m=matrix(B,B,x,y,v[x-y+B+1]);\
                q=qflll(m,4)[1];if(length(q)==0,return(0));\
                p=sum(k=1,B,x^(k-1)*q[k,1]);\
                q=Pol(Pol(vector(l,n,v[l-n+1]))*p+O(x^(B+1)));\
                if(polcoeff(p,0)<0,q=-q;p=-p);q=q/p;p=Ser(q+O(x^(l+1)));\
                for(m=1,l,if(polcoeff(p,m-1)!=v[m],return(0)));q")
            _gp.set('gf', sequence)
            _gp("gf=ggf(gf)")
            num = S(sage_eval(_gp.eval("Vec(numerator(gf))"))[::-1])
            den = S(sage_eval(_gp.eval("Vec(denominator(gf))"))[::-1])
            if num == 0:
                return 0
            else:
                return CFiniteSequence(num / den)
        else:
            from sage.matrix.constructor import matrix
            from sage.functions.other import floor, ceil
            from numpy import trim_zeros
            l = len(sequence)
            if l < 6:
                raise ValueError('Sequence too short for guessing.')

            hl = ceil(ZZ(l)/2)
            A = matrix([sequence[k:k+hl] for k in range(hl)])
            K = A.kernel()
            if K.dimension() == 0:
                return 0
            R = PolynomialRing(QQ, 'x')
            den = R(trim_zeros(K.basis()[-1].list()[::-1]))
            if den == 1:
                return 0
            offset = next((i for i, x in enumerate(sequence) if x!=0), None)
            S = PowerSeriesRing(QQ, 'x', default_prec=l-offset)
            num = S(R(sequence)*den).add_bigoh(floor(ZZ(l)/2+1)).truncate()
            if num == 0 or sequence != S(num/den).list():
                return 0
            else:
                return CFiniteSequence(num / den)

"""
EXAMPLES::

    sage: r.egf()      # not implemented
    exp(2*x)

.. TODO::

    sage: CFiniteSequence(x+x^2+x^3+x^4+x^5+O(x^6)) # not implemented
    ... x/(1-x)
    sage: latex(r)        # not implemented
    \big\{a_{n\ge0}\big|a_{n+2}=\sum_{i=0}^{1}c_ia_{n+i}, c=\{1,1\}, a_{n<2}=\{0,0,0,1\}\big\}

Given a multivariate generating function, the generating coefficient must
be given as extra parameter::

    sage: r = CFiniteSequence(1/(1-y-x*y), x) # not tested
"""
