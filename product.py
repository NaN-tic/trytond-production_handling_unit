# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.

from trytond.model import fields
from trytond.pool import PoolMeta


class Product(metaclass=PoolMeta):
    __name__ = 'product.product'

    production_handling_unit_assignments = fields.One2Many(
        'production.work.center.handling_unit.assignment', 'product',
        'Production Handling Unit Assignments')
