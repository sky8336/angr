import logging
import os
import angr.analyses.reaching_definitions as rdef
import angr
import cffi
import nose
from angr.calling_conventions import DEFAULT_CC

l = logging.getLogger('angr.test_command_injections')

arches = ['aarch64', 'armel', 'armhf']
arches += ['mips', 'mipsel']
# arches += ['mips64', 'mips64el']
arches += ['ppc', 'ppcspe']
# arches += ['ppc64', 'ppc64le']
arches = ['x86_64']


def strcpy(reach_def_ana):
    # FIXME: assuming x64
    first_args = [k for k, v in reach_def_ana.arch.argument_register_positions.iteritems() if v == 0]
    second_args = [k for k, v in reach_def_ana.arch.argument_register_positions.iteritems() if v == 1]

    for f_arg in first_args:
        defs = reach_def_ana.state.register_definitions.get_variables_by_offset(f_arg)

        # FIXME: multiple register might have the same argument index, only one should be set though
        for d in defs:
            # add a use for each def of the source buffer
            reach_def_ana.state.register_uses.add_use(d, reach_def_ana._codeloc())

            # add a def for each dest buffer
            for s_arg in second_args:
                reach_def_ana.state.kill_and_add_definition(rdef.Register(s_arg, reach_def_ana.arch.bits),
                                                            reach_def_ana._codeloc(), d.data)

            # def for the return register (same pointer as dst buffer)
            # FIXME: here it gets only the last one
            reach_def_ana.state.kill_and_add_definition(rdef.Register(reach_def_ana.arch.ret_offset,reach_def_ana.arch.bits),
                                                            reach_def_ana._codeloc(), d.data)


function_summaries = {'strcpy': strcpy}
arches += ['i386', 'x86_64']


def run_command_injection(arch, binary):
    parent_dir = os.path.dirname(os.path.realpath(__file__))
    binary_dir = os.path.realpath(os.path.join(parent_dir, '../../binaries/tests'))

    binary_path = str(os.path.realpath(os.path.join(binary_dir, arch, binary)))
    import ipdb; ipdb.set_trace()
    p = angr.Project(binary_path, auto_load_libs=False)
    cfg = p.analyses.CFGFast()

    nose.tools.assert_in('system', cfg.functions)
    func_system = cfg.functions['system']

    # FIXME: handle multiple nodes
    # FIXME: replace explicit search for main with inter function analysis
    node_caller = cfg.get_all_nodes(func_system.addr)[0].predecessors[0]
    while True:
        if node_caller.name is None or node_caller.name.find('main') < 0:
            node_caller = node_caller.predecessors[0]
        else:
            break

    func_caller = cfg.functions[node_caller.function_address]

    # FIXME: fix node_caller.instruction_addrs in thumb mode
    if node_caller.addr % 2 == 1:
        node_caller = p.factory.block(node_caller.addr, thumb=True)

    ops = [(node_caller.instruction_addrs[-1], angr.analyses.reaching_definitions.OP_BEFORE)]
    rda = p.analyses.ReachingDefinitions(func=func_caller, observation_points=ops, init_func=True, function_summaries=function_summaries)
    rd = rda.observed_results[ops[0]]

    # FIXME: get CC from analysis
    cc = DEFAULT_CC[p.arch.name]

    # FIXME: iterate over all results
    if len(cc.ARG_REGS) == 0:
        sp_offset = p.arch.sp_offset
        dd = next(iter(rd.register_definitions.get_objects_by_offset(sp_offset)))
        d = next(iter(rd.memory_definitions.get_objects_by_offset(dd.data)))
    else:
        reg_offset = p.arch.registers[cc.ARG_REGS[0]][0]
        d = next(iter(rd.register_definitions.get_objects_by_offset(reg_offset)))

    cmd = cffi.FFI().string(cfg._fast_memory_load(d.data))
    nose.tools.assert_equal(cmd, 'ls', 'arch: %s, binary: %s' % (arch, binary))


def test_all():
    for arch in arches:
        run_command_injection(arch, 'system_command_03')


if __name__ == '__main__':
    test_all()
