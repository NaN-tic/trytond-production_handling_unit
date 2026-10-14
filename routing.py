# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from sql.conditionals import Coalesce

from trytond.model import ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction


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

    handling_unit_source_operations = fields.Many2Many(
        'production.routing.operation-handling_unit.source',
        'operation', 'source_operation',
        'Operations to Retrieve Cycles From')


class RoutingStep(metaclass=PoolMeta):
    __name__ = 'production.routing.step'

    handling_unit = fields.Many2One('production.handling_unit', 'Handling Unit')
    show_handling_unit_values = fields.Boolean('Show Handling Unit Values')

    @staticmethod
    def default_show_handling_unit_values():
        return True

    @classmethod
    def __register__(cls, module):
        handler = cls.__table_handler__(module)
        migrate_unit = not handler.column_exist('handling_unit')
        migrate_show = not handler.column_exist('show_handling_unit_values')
        super().__register__(module)

        Operation = Pool().get('production.routing.operation')
        operation_handler = Operation.__table_handler__(module)
        operation = Operation.__table__()
        table = cls.__table__()
        cursor = Transaction().connection.cursor()
        if migrate_unit and operation_handler.column_exist('handling_unit'):
            cursor.execute(*table.update([table.handling_unit], [
                operation.select(operation.handling_unit,
                    where=operation.id == table.operation)]))
        if migrate_show:
            value = True
            if operation_handler.column_exist('show_handling_unit_values'):
                value = Coalesce(operation.select(
                    operation.show_handling_unit_values,
                    where=operation.id == table.operation), True)
            cursor.execute(*table.update([table.show_handling_unit_values],
                [value]))

    def get_work(self, production, work_center_picker):
        work = super().get_work(production, work_center_picker)
        work.routing_step = self
        return work
