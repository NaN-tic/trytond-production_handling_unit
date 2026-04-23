# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import hashlib

from trytond.exceptions import UserWarning
from trytond.i18n import gettext
from trytond.model import ModelSQL, ModelView, Unique, fields, sequence_ordered
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction


class HandlingUnit(ModelSQL, ModelView):
    'Handling Unit'
    __name__ = 'production.handling_unit'

    name = fields.Char('Name', required=True)
    code = fields.Char('Code')
    company = fields.Many2One('company.company', 'Company', required=True)
    active = fields.Boolean('Active')
    description = fields.Text('description')

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_active():
        return True


class WorkCenterHandlingUnitAssignment(ModelSQL, ModelView):
    'Work Center Handling Unit Assignment'
    __name__ = 'production.work.center.handling_unit.assignment'

    company = fields.Many2One('company.company', 'Company', required=True)
    work_center = fields.Many2One(
        'production.work.center', 'Work Center', required=True,
        domain=[
            ('company', '=', Eval('company', -1)),
            ('category.is_line', '=', True),
            ],
        depends=['company'])
    product = fields.Many2One(
        'product.product', 'Product', required=True,
        context={
            'company': Eval('company', -1),
            },
        depends=['company'])
    uom = fields.Many2One('product.uom', 'UoM', required=True)
    handling_unit = fields.Many2One(
        'production.handling_unit', 'Handling Unit', required=True,
        domain=[
            ('company', '=', Eval('company', -1)),
            ],
        depends=['company'])
    quantity = fields.Float('Quantity', required=True)
    active = fields.Boolean('Active')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        table = cls.__table__()
        cls._sql_constraints += [
            ('work_center_product_handling_unit_uniq',
                Unique(table, table.company, table.work_center, table.product,
                    table.handling_unit),
                'The assignment must be unique per company, work center, '
                'product and handling unit.'),
            ]

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_active():
        return True

class WorkCenter(sequence_ordered(), metaclass=PoolMeta):
    __name__ = 'production.work.center'

    handling_unit_assignments = fields.One2Many(
        'production.work.center.handling_unit.assignment', 'work_center',
        'Handling Unit Assignments',
        domain=[
            ('company', '=', Eval('company', -1)),
            ],
        depends=['company'])


class WorkCycle(metaclass=PoolMeta):
    __name__ = 'production.work.cycle'

    handling_unit = fields.Many2One(
        'production.handling_unit', 'Handling Unit',
        domain=[
            ('company', '=', Eval('company', -1)),
            ],
        states={
            'readonly': Eval('state').in_(['done', 'cancelled']),
            },
        depends=['company', 'state'])
    handling_unit_number = fields.Integer(
        'Handling Unit Number',
        states={
            'readonly': Eval('state').in_(['done', 'cancelled']),
            },
        depends=['state'])
    missing_units = fields.Float(
        'Missing Units',
        states={
            'readonly': Eval('state').in_(['done', 'cancelled']),
            },
        depends=['state'])

    @classmethod
    def _get_operation_handling_unit_from_work(cls, work):
        if not work or not work.operation:
            return None
        return work.operation.handling_unit

    @classmethod
    def _get_assignment_from_work(cls, work):
        pool = Pool()
        Assignment = pool.get('production.work.center.handling_unit.assignment')

        if not work:
            return None
        if not work.production or not work.production.product:
            return None

        line = work.production.line
        if not line:
            return None

        assignments = Assignment.search([
            ('company', '=', work.production.company.id),
            ('work_center', '=', line.id),
            ('product', '=', work.production.product.id),
            ('active', '=', True),
            ], limit=1)
        return assignments[0] if assignments else None

    @classmethod
    def _get_handling_unit_from_work(cls, work):
        operation_handling_unit = cls._get_operation_handling_unit_from_work(
            work)
        if operation_handling_unit:
            return operation_handling_unit
        assignment = cls._get_assignment_from_work(work)
        return assignment.handling_unit if assignment else None

    @classmethod
    def _get_work_from_context(cls):
        pool = Pool()
        Work = pool.get('production.work')

        work_id = Transaction().context.get('default_work')
        if not work_id:
            return None
        return Work(work_id)

    @fields.depends('work', 'handling_unit_number')
    def on_change_work(self):
        if not self.work:
            return
        handling_unit = self._get_handling_unit_from_work(self.work)
        if handling_unit:
            self.handling_unit = handling_unit

    @classmethod
    def create(cls, vlist):
        pool = Pool()
        Work = pool.get('production.work')

        vlist = [values.copy() for values in vlist]
        work_ids = {values.get('work') for values in vlist if values.get('work')}
        works = {w.id: w for w in Work.browse(work_ids)}
        for values in vlist:
            work = works.get(values.get('work'))
            if not work:
                continue
            handling_unit = cls._get_handling_unit_from_work(work)
            if handling_unit:
                values.setdefault('handling_unit', handling_unit.id)
        return super().create(vlist)

    @classmethod
    def default_get(cls, fields_names, with_rec_name=True):
        defaults = super().default_get(fields_names, with_rec_name=with_rec_name)

        work = cls._get_work_from_context()
        if not work:
            return defaults

        handling_unit = cls._get_handling_unit_from_work(work)
        if handling_unit:
            if ('handling_unit' in fields_names
                    and not defaults.get('handling_unit')):
                defaults['handling_unit'] = handling_unit.id
        return defaults

    @classmethod
    def validate(cls, cycles):
        super().validate(cycles)
        cls.check_duplicate_handling_unit_number(cycles)

    @classmethod
    def check_duplicate_handling_unit_number(cls, cycles):
        Warning = Pool().get('res.user.warning')

        for cycle in cycles:
            if (not cycle.handling_unit_number
                    or cycle.state in {'done', 'cancelled'}
                    or not cycle.work or not cycle.work.operation):
                continue

            duplicates = cls.search([
                ('handling_unit_number', '=', cycle.handling_unit_number),
                ('work.production.state', 'not in', ['done', 'cancelled']),
                ('work.production', '=', cycle.work.production.id),
                ], limit=1)

            if not duplicates:
                continue

            duplicate = duplicates[0]
            refs = [
                str(cycle.work.production.id if cycle.work.production else ''),
                str(cycle.work.operation.id if cycle.work.operation else ''),
                str(cycle.handling_unit_number),
                str(duplicate.id),
                ]
            key = 'work_cycle_duplicate_handling_unit_number_%s' % hashlib.md5(
                '_'.join(refs).encode('utf-8')).hexdigest()
            if Warning.check(key):
                raise UserWarning(
                    key,
                    gettext(
                        'production_handling_unit.'
                        'msg_work_cycle_duplicate_handling_unit_number',
                        handling_unit_number=cycle.handling_unit_number,
                        production=duplicate.work.production.rec_name,
                        operation=duplicate.work.operation.rec_name))
