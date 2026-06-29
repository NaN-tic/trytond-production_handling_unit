# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelSQL, fields
from trytond.pool import PoolMeta


class RoutingOperationHandlingUnitSource(ModelSQL):
    'Routing Operation Handling Unit Source'
    __name__ = 'production.routing.operation-handling_unit.source'

    operation = fields.Many2One(
        'production.routing.operation', 'Operation',
        required=True, ondelete='CASCADE')
    source_operation = fields.Many2One(
        'production.routing.operation', 'Source Operation',
        required=True, ondelete='CASCADE')


class RoutingOperation(metaclass=PoolMeta):
    __name__ = 'production.routing.operation'

    handling_unit = fields.Many2One('production.handling_unit', 'Handling Unit')
    handling_unit_source_operations = fields.Many2Many(
        'production.routing.operation-handling_unit.source',
        'operation', 'source_operation',
        'Handling Unit Source Operations')
