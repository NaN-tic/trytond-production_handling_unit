# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from sql.conditionals import Coalesce

from trytond.model import ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
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

    handling_unit_configurations = fields.One2Many(
        'production.operation.handling_unit', 'operation',
        'Handling Unit Configuration')

    handling_unit_source_operations = fields.Many2Many(
        'production.routing.operation-handling_unit.source',
        'operation', 'source_operation',
        'Operations to Retrieve Cycles From')


class RoutingStep(metaclass=PoolMeta):
    __name__ = 'production.routing.step'

    handling_unit = fields.Many2One('production.handling_unit', 'Handling Unit',
        states={'invisible': Eval('handling_unit_mode') == 'inherit'},
        depends=['handling_unit_mode'])
    show_handling_unit_values = fields.Boolean('Show Handling Unit Values')
    handling_unit_mode = fields.Selection([
        ('inherit', 'Inherit from Operation'), ('none', 'Do Not Request'),
        ('input', 'Enter Container'),
        ('previous', 'Retrieve Previous Container'),
        ], 'Handling Unit Behaviour', required=True)
    handling_unit_number_required = fields.Boolean('Container Number Required',
        states={'invisible': Eval('handling_unit_mode') == 'inherit'},
        depends=['handling_unit_mode'])
    handling_unit_uom = fields.Many2One('product.uom', 'UoM',
        help='Leave empty to use the production unit.',
        states={'invisible': Eval('handling_unit_mode') == 'inherit'},
        depends=['handling_unit_mode'])
    show_missing_units = fields.Boolean('Request Missing Units',
        states={'invisible': Eval('handling_unit_mode') == 'inherit'},
        depends=['handling_unit_mode'])
    handling_unit_exceptions = fields.One2Many(
        'production.step.handling_unit.exception', 'step',
        'Product and Category Exceptions')

    @staticmethod
    def default_handling_unit_mode():
        return 'inherit'

    @staticmethod
    def default_show_missing_units():
        return True

    @classmethod
    def create(cls, vlist):
        vlist = [values.copy() for values in vlist]
        for values in vlist:
            # Preserve callers using the previous step configuration API.
            if ('handling_unit' in values
                    or 'show_handling_unit_values' in values):
                values.setdefault('handling_unit_mode',
                    'input' if values.get('show_handling_unit_values', True)
                    else 'none')
        return super().create(vlist)

    @classmethod
    def write(cls, *args):
        actions = []
        for records, values in zip(args[0::2], args[1::2]):
            values = values.copy()
            if ('show_handling_unit_values' in values
                    and 'handling_unit_mode' not in values):
                values['handling_unit_mode'] = (
                    'input' if values['show_handling_unit_values'] else 'none')
            actions.extend((records, values))
        super().write(*actions)

    @staticmethod
    def default_show_handling_unit_values():
        return True

    @classmethod
    def __register__(cls, module):
        handler = cls.__table_handler__(module)
        migrate_unit = not handler.column_exist('handling_unit')
        migrate_show = not handler.column_exist('show_handling_unit_values')
        migrate_mode = not handler.column_exist('handling_unit_mode')
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
        if migrate_mode:
            cursor.execute(*table.update(
                [table.handling_unit_mode, table.show_missing_units],
                ['input', True]))
            cursor.execute(*table.update([table.handling_unit_mode], ['none'],
                where=table.show_handling_unit_values == False))

    def get_work(self, production, work_center_picker):
        work = super().get_work(production, work_center_picker)
        work.routing_step = self
        return work
