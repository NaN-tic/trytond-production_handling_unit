# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import hashlib

from trytond.exceptions import UserError, UserWarning
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
                'production_handling_unit.'
                'msg_work_center_product_handling_unit_unique'),
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


class Work(metaclass=PoolMeta):
    __name__ = 'production.work'

    routing_step = fields.Many2One(
        'production.routing.step', 'Routing Step', readonly=True,
        ondelete='SET NULL')

    @classmethod
    def __register__(cls, module):
        super().__register__(module)
        # Link existing works only when the routing, operation and sequence
        # identify a single step. Never guess between repeated operations.
        cursor = Transaction().connection.cursor()
        cursor.execute("""
            UPDATE production_work
            SET routing_step = (
                SELECT MIN(s.id) FROM production_routing_step s
                JOIN production p ON p.routing = s.routing
                WHERE p.id = production_work.production
                    AND s.operation = production_work.operation
                    AND (s.sequence = production_work.sequence
                        OR (s.sequence IS NULL
                            AND production_work.sequence IS NULL)))
            WHERE routing_step IS NULL AND (
                SELECT COUNT(*) FROM production_routing_step s
                JOIN production p ON p.routing = s.routing
                WHERE p.id = production_work.production
                    AND s.operation = production_work.operation
                    AND (s.sequence = production_work.sequence
                        OR (s.sequence IS NULL
                            AND production_work.sequence IS NULL))) = 1
            """)

    def get_handling_unit(self):
        return self.get_handling_unit_policy()['handling_unit']

    def get_handling_unit_policy(self):
        """Resolve product, category, step and company-operation settings."""
        step = self.routing_step
        company = self.production.company if self.production else self.company
        configurations = self.operation.handling_unit_configurations
        configuration = next((item for item in configurations
            if item.company == company), None)
        inherited = not step or step.handling_unit_mode == 'inherit'
        unit = None
        mode = 'none'
        required = False
        uom = None
        missing = False
        if inherited and configuration:
            unit = configuration.handling_unit
            mode = configuration.mode
            required = configuration.number_required
            uom = configuration.uom
            missing = configuration.show_missing_units
        elif step:
            unit = step.handling_unit
            mode = step.handling_unit_mode
            if mode == 'inherit':
                mode = 'input' if step.show_handling_unit_values else 'none'
            required = step.handling_unit_number_required
            uom = step.handling_unit_uom
            missing = step.show_missing_units

        # Source operations may supply the container type without a product
        # assignment. Do not recurse: routings may contain circular sources.
        if not unit and step:
            for operation in sorted(
                    self.operation.handling_unit_source_operations,
                    key=lambda item: item.id):
                for source in step.routing.steps:
                    if source.operation != operation:
                        continue
                    source_config = next((item for item in
                        operation.handling_unit_configurations
                        if item.company == company), None)
                    if (source.handling_unit_mode == 'inherit'
                            and source_config):
                        unit = source_config.handling_unit
                    else:
                        unit = source.handling_unit
                    if unit:
                        break
                if unit:
                    break

        product = getattr(self.production, 'product', None)
        if step and product:
            category_ids = set()
            for category in product.template.categories:
                while category and category.id not in category_ids:
                    category_ids.add(category.id)
                    category = category.parent
            product_matches, category_matches = set(), set()
            for rule in step.handling_unit_exceptions:
                if product in rule.products:
                    product_matches.add(rule.request)
                elif category_ids & {c.id for c in rule.categories}:
                    category_matches.add(rule.request)
            matches = product_matches or category_matches
            if len(matches) > 1:
                raise UserError(gettext(
                    'production_handling_unit.msg_exception_conflict',
                    step=step.rec_name))
            if matches:
                request, = matches
                if not request:
                    mode = 'none'
                elif mode == 'none':
                    mode = 'input'
        if mode != 'none' and unit and company and unit.company != company:
            raise UserError(gettext(
                'production_handling_unit.msg_policy_company'))
        # Unconfigured legacy steps never requested a container.
        if not unit and not configuration and not (
                step and step.handling_unit_exceptions):
            mode = 'none'
        return {'mode': mode, 'handling_unit': unit,
            'number_required': required, 'uom': uom,
            'show_missing_units': missing,
            'configured': bool(configuration or step)}


class WorkCycle(metaclass=PoolMeta):
    __name__ = 'production.work.cycle'

    handling_unit_policy = fields.Selection([
        ('none', 'Do Not Request'), ('input', 'Enter Container'),
        ('previous', 'Retrieve Previous Container'),
        ], 'Handling Unit Behaviour', readonly=True)
    handling_unit_number_required = fields.Boolean(
        'Container Number Required', readonly=True)
    handling_unit_uom = fields.Many2One('product.uom', 'UoM', readonly=True)
    show_missing_units = fields.Boolean('Request Missing Units', readonly=True)
    handling_unit_source_cycle = fields.Many2One('production.work.cycle',
        'Source Container Cycle', readonly=True, ondelete='RESTRICT')

    @classmethod
    def __register__(cls, module):
        handler = cls.__table_handler__(module)
        migrate = not handler.column_exist('handling_unit_policy')
        super().__register__(module)
        if migrate:
            table = cls.__table__()
            cursor = Transaction().connection.cursor()
            cursor.execute(*table.update(
                [table.handling_unit_policy, table.show_missing_units,
                    table.handling_unit_number_required],
                ['none', True, False]))
            cursor.execute(*table.update([table.handling_unit_policy],
                ['input'], where=table.handling_unit != None))
            # Preserve the unit previously obtained from the product-line
            # assignment when displaying historical cycles.
            cursor.execute("""
                UPDATE production_work_cycle AS cycle
                SET handling_unit_uom = (
                    SELECT assignment.uom
                    FROM production_work AS work
                    JOIN production AS production
                        ON production.id = work.production
                    JOIN production_work_center_handling_unit_assignment
                        AS assignment
                        ON assignment.company = production.company
                        AND assignment.work_center = production.line
                        AND assignment.product = production.product
                        AND assignment.handling_unit = cycle.handling_unit
                    WHERE work.id = cycle.work AND assignment.active
                    LIMIT 1)
                WHERE cycle.handling_unit IS NOT NULL
                """)

    def get_handling_unit_policy(self):
        if not self.handling_unit_policy:
            return self.work.get_handling_unit_policy()
        return {'mode': self.handling_unit_policy,
            'handling_unit': self.handling_unit,
            'number_required': self.handling_unit_number_required,
            'uom': self.handling_unit_uom,
            'show_missing_units': self.show_missing_units}

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
        if not work:
            return None
        policy = work.get_handling_unit_policy()
        return policy['handling_unit'] if policy['mode'] != 'none' else None

    @classmethod
    def _get_work_from_context(cls):
        pool = Pool()
        Work = pool.get('production.work')

        work_id = Transaction().context.get('default_work')
        if not work_id:
            return None
        return Work(work_id)

    @fields.depends(
        'work',
        '_parent_work.routing_step',
        '_parent_work.production',
        'handling_unit_number')
    def on_change_work(self):
        if not self.work:
            return
        handling_unit = self._get_handling_unit_from_work(self.work)
        if handling_unit:
            self.handling_unit = handling_unit

    @classmethod
    def preprocess_values(cls, mode, values):
        values = super().preprocess_values(mode, values)
        if mode != 'create' or not values.get('work'):
            return values

        pool = Pool()
        Work = pool.get('production.work')
        work = Work(values['work'])
        policy = work.get_handling_unit_policy()
        if (policy['mode'] == 'none' and not policy['configured']
                and values.get('handling_unit')):
            policy['mode'] = 'input'
        values['handling_unit_policy'] = policy['mode']
        values['handling_unit_number_required'] = policy['number_required']
        values['handling_unit_uom'] = (
            policy['uom'].id if policy['uom'] else None)
        values['show_missing_units'] = policy['show_missing_units']
        if policy['mode'] == 'none':
            values['handling_unit'] = None
            values['handling_unit_number'] = None
        elif policy['handling_unit'] and not values.get('handling_unit'):
            values['handling_unit'] = policy['handling_unit'].id
        return values

    @classmethod
    def write(cls, *args):
        actions = []
        for cycles, values in zip(args[0::2], args[1::2]):
            for cycle in cycles:
                updated = values.copy()
                if (cycle.state == 'draft' and values.get('handling_unit')
                        and cycle.handling_unit_policy == 'none'):
                    policy = cycle.work.get_handling_unit_policy()
                    if policy['mode'] != 'none':
                        updated.update(
                            handling_unit_policy=policy['mode'],
                            handling_unit_number_required=policy[
                                'number_required'],
                            handling_unit_uom=(policy['uom'].id
                                if policy['uom'] else None),
                            show_missing_units=policy['show_missing_units'])
                actions.extend(([cycle], updated))
        super().write(*(actions or args))

    @classmethod
    def default_get(
            cls, fields_names=None, with_rec_name=True, with_default=True):
        if fields_names is None:
            fields_names = cls._fields.keys()
        defaults = super().default_get(
            fields_names, with_rec_name=with_rec_name,
            with_default=with_default)

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
    def validate_fields(cls, cycles, field_names):
        super().validate_fields(cycles, field_names)
        if field_names is None or {
                'work', 'handling_unit', 'handling_unit_number', 'state'
                } & set(field_names):
            for cycle in cycles:
                if cycle.state != 'running':
                    continue
                policy = cycle.get_handling_unit_policy()
                if policy['mode'] == 'none':
                    continue
                if (not cycle.handling_unit
                        or cycle.handling_unit.company != cycle.company):
                    raise UserError(gettext(
                        'production_handling_unit.msg_policy_unit_required'))
                if policy['number_required'] and (
                        cycle.handling_unit_number is None
                        or cycle.handling_unit_number <= 0):
                    raise UserError(gettext(
                        'production_handling_unit.msg_policy_number_required'))
                if policy['mode'] == 'previous':
                    source = cycle.handling_unit_source_cycle
                    if (not source or source == cycle
                            or source.work.production != cycle.work.production
                            or source.handling_unit != cycle.handling_unit
                            or source.handling_unit_number
                            != cycle.handling_unit_number):
                        raise UserError(gettext(
                            'production_handling_unit.msg_policy_source_required'))
        if field_names is None or {
                'work', 'handling_unit_number', 'state'} & set(field_names):
            cls.check_duplicate_handling_unit_number(cycles)

    @classmethod
    def check_duplicate_handling_unit_number(cls, cycles):
        Warning = Pool().get('res.user.warning')

        for cycle in cycles:
            if (not cycle.handling_unit_number
                    or cycle.state in {'done', 'cancelled'}
                    or not cycle.work or not cycle.work.operation):
                continue

            domain = [
                ('handling_unit_number', '=', cycle.handling_unit_number),
                ('state', 'not in', ['done', 'cancelled']),
                ('work.production.state', 'not in', ['done', 'cancelled']),
                ('work.production', '=', cycle.work.production.id),
                ]
            if cycle.id:
                domain.append(('id', '!=', cycle.id))
            if cycle.work.sequence is not None:
                domain.append(('work.sequence', '>=', cycle.work.sequence))
            else:
                domain.append(('work.operation', '=', cycle.work.operation.id))

            duplicates = cls.search(domain, limit=1)

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
