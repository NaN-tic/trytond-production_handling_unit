# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta


class RoutingOperation(metaclass=PoolMeta):
    __name__ = 'production.routing.operation'

    handling_unit = fields.Many2One('production.handling_unit', 'Handling Unit')
