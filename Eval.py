import re
# vim: set fileencoding=utf8:

class EvalException:
    def __init__ (self, msg):
        self.msg = msg

    def __repr__ (self):
        return self.msg

class Continue:
    pass

class Eval:
    OP_BINARY_IMPL = {
        '+': lambda x, y: x + y,
        '-': lambda x, y: x - y,
        '*': lambda x, y: x * y,
        '/': lambda x, y: x / y,
        '>': lambda x, y: x > y,
        '<': lambda x, y: x < y,
        '>=': lambda x, y: x >= y,
        '<=': lambda x, y: x <= y,
        '==': lambda x, y: x == y,
        '!=': lambda x, y: x != y,
        '||': lambda x, y: x or y,
        '&&': lambda x, y: x and y,
        ':': 'op_value_subscription',
        ':*': 'eval_value_subscription',
    }

    def __init__ (self, parser, data = {}):
        self.parser = parser
        self.data = data
        self.env = {
            'variables': {},
            'functions': parser.functions,
        }
        self.predefined_function = PredefinedFunction(self)
        self.stack = []
        self.initialize_variables()
        self.reorder_functions()

    def initialize_variables (self):
        self.env['variables'].setdefault(
            'MASTER', 0 # XXX 0 でいい？
        )
        self.env['variables'].setdefault(
            'NAME', { 0: u'あなた' } # TODO CSV から
        )

    def reorder_functions (self):
        for functions in self.env['functions'].values():
            functions.sort(
                lambda f, g: 
                    -1 if f.get('prop') == 'PRI' else +1 if f.get('prop') == 'LAST' else 0
            )

    def eval_lvalue (self, value):
        (name, subs) = (value[0], value[1]) # ex. ( 'TALENT', [ 'ASSI', '83' ] )
        if re.match(':', name):
            print name
        dic = self.env['variables']
        for s in subs:
            (dic, name) = (dic.setdefault(name, {}), self.eval_expr(s))
        return (dic, name)

    def eval_atom (self, atom, expect = int):
        if re.match('^-?\d+$', atom):
            return int(atom)
        else:
            return expect(self.env['variables'].setdefault(atom, expect()))

    def op_value_subscription (self, x, y, expect = int):
        value = self.eval_expr(x, dict)
        key = self.eval_expr(y)
        return value.setdefault(key, expect())

    def eval_op (self, op, args, expect = int):
        bin_op = self.OP_BINARY_IMPL[op]
        if isinstance(bin_op, str):
            return getattr(self, bin_op)(args[0], args[1], expect)
        else:
            return bin_op(self.eval_expr(args[0], expect), self.eval_expr(args[1], expect))

    def eval_expr (self, expr, expect = int):
        if isinstance(expr, dict):
            return self.eval_op(expr['operator'], expr['operand'], expect)
        else:
            return self.eval_atom(expr, expect)

    def eval_statement (self, stmt):
        # print '# eval_statement', stmt
        if stmt['type'] == 'LET':
            (dic, name) = self.eval_lvalue(stmt['lhs'])
            print '%s = %s' % (stmt['lhs'], self.eval_expr(stmt['rhs']))
            dic[name] = self.eval_expr(stmt['rhs'])

        elif stmt['type'] == 'IF':
            for (cond, block) in stmt['cond']:
                if self.eval_expr(cond):
                    self.eval_block(block)
                    break
            else:
                self.eval_block(stmt['else'])

        elif stmt['type'] == 'REPEAT':
            count = self.eval_expr(stmt['count'])
            for i in range(count):
                print i, range(count)
                self.variables['COUNT'] = i
                try:
                    self.eval_block(stmt['block'])
                except Continue, c:
                    print '# continue'
                    continue

        elif stmt['type'] == 'FUNC_CALL':
            name = stmt['funcname'].upper()
            predefined = getattr(self.predefined_function, name, None)
            if predefined:
                predefined(stmt['args'])
            else:
                self.predefined_function.CALL(name)

        elif stmt['type'] == 'CONTINUE':
            raise Continue()

        elif stmt['type'] == 'LABEL':
            self.current_frame().labels[stmt['name']] = self.current_frame().next_index

        else:
            print 'Could not handle stmt: %s' % stmt

    def current_frame (self):
        return self.stack[-1]

    def eval_block (self, block):
        frame = Frame(block)
        self.stack.append(frame)

        try:
            while self.eval_next_statement():
                pass
        finally:
            if self.current_frame() == frame:
                self.stack.pop()

    def eval_next_statement (self):
        if self.current_frame().at_last():
            return False

        statement = self.current_frame().next_statement()
        self.current_frame().step()
        self.eval_statement(statement)

        return True

class PredefinedFunction:
    def __init__ (self, e):
        self.eval = e

    def CALL (self, name):
        print '# CALL %s' % name
        func = self.eval.env['functions'].get(name)
        if func is None:
            raise EvalException('Function does not exist: \'%s\'' % name)
        self.eval.eval_block(func[-1]['body']) # XXX calling last defined function # TODO args
        print '# CALL %s END' % name
        # TODO RETURN 0

    def DRAWLINE (self, args):
        print '----------'

    # 改行なしの印字
    def PRINT (self, arg):
        print arg,

    # 改行つき印字
    def PRINTL (self, arg):
        print arg

    # 値の印字
    def PRINTV (self, expr):
        print self.eval.eval_expr(expr),

    # フォーマット指定印字 + 入力待ち + 改行
    def PRINTFORMW (self, arg):
        self.PRINTFORM(arg)
        raw_input()
        print

    # フォーマット指定印字 + 改行
    def PRINTFORML (self, arg):
        self.PRINTFORM(arg)
        print

    # フォーマット指定印字
    def PRINTFORM (self, arg):
        s = re.Scanner([
            (r'%.*?%',  lambda _, expr: unicode(self.eval.eval_expr(self.eval.parser.parse_expr(expr[1:-1])))),
            (r'{.*?}',  lambda _, expr: unicode(self.eval.eval_expr(self.eval.parser.parse_expr(expr[1:-1])))),
            (r'[^%{]*', lambda _, s: s)
        ])
        parsed = s.scan(arg)
        print ''.join(parsed[0] + [parsed[1]]),

    # ショップで売っているアイテムの表示
    def PRINT_SHOPITEM (self, args):
        # print 'FLAG', self.eval.env['variables']['FLAG']
        # print 'ITEMSALES', self.eval.env['variables']['ITEMSALES']
        import pprint
        pprint.PrettyPrinter(indent = 2).pprint(self.eval.env['variables']['ITEMSALES'])
        print '# stub PRINT_SHOPITEM'
        itemsales = self.eval.env['variables']['ITEMSALES']
        i = 0
        for n in itemsales:
            data = self.eval.data['Item'].get(n)
            if itemsales[n] and data:
                print '[%3d] %s \\%d' % (n, data[0], int(data[1])),
                i += 1
                if i % 3 == 0:
                    print
                else:
                    print "\t\t",
        else:
            if i % 3 != 0:
                print

    # 所持アイテムの表示
    def PRINT_ITEM (self, args):
        print '# stbu PRINT_ITEM'

    def INPUT (self, args):
        self.eval.env['variables']['RESULT'] = raw_input()

    def GOTO (self, label):
        while True:
            index = self.eval.current_frame().labels.get(label)
            if index is None:
                self.eval.stack.pop()
                continue
            self.eval.current_frame().next_index = index
            break
        else:
            raise EvalException('Could not find label \'%s\'' % label)

    def RETURN (self, expr):
        self.eval.env['variables']['RESULT'] = self.eval.eval_expr(expr)
        self.eval.current_frame().next_index = -1

    def BEGIN (self, what):
        # TODO フレームスタックをクリア?
        if what == 'SHOP':
            self.CALL('SHOW_SHOP')
            # TODO 購入うんぬん
            item_id = int(raw_input())
            if 0 <= item_id <= 99:
                itemsales = self.eval.eval_value_subscription([ 'ITEMSALES', item_id  ])
                print '# itemsales: %s' % itemsales
            else:
                self.eval.env['variables']['RESULT'] = item_id
                self.CALL('USERSHOP')
        else:
            raise EvalException('Could not BEGIN \'%s\'' % what)

class Frame:
    def __init__ (self, block):
        self.block = block
        self.next_index = 0
        self.labels = {}

    def at_last (self):
        return self.next_index >= len(self.block) or self.next_index == -1

    def next_statement (self):
        return self.block[self.next_index]

    def step (self):
        self.next_index += 1
