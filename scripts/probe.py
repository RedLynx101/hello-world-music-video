import bpy, sys
sc = bpy.context.scene
print('VERSION', bpy.app.version_string)
print('ENGINES', [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items])
ee = sc.eevee
print('EEVEE_PROPS', [p.identifier for p in ee.bl_rna.properties if any(k in p.identifier for k in ('ray', 'taa', 'sample', 'shadow', 'volum', 'fast', 'gi', 'clamp', 'bloom'))])
print('IMG_FORMATS', [e.identifier for e in bpy.types.ImageFormatSettings.bl_rna.properties['file_format'].enum_items])
print('EXR_CODECS', [e.identifier for e in bpy.types.ImageFormatSettings.bl_rna.properties['exr_codec'].enum_items])
print('VIEW_TRANSFORMS', [e.identifier for e in sc.view_settings.bl_rna.properties['view_transform'].enum_items])
print('SCENE_HAS', [a for a in ('use_nodes', 'compositing_node_group', 'node_tree') if hasattr(sc, a)])
w = bpy.data.worlds.new('probe')
print('WORLD_USE_NODES', hasattr(w, 'use_nodes'))
m = bpy.data.materials.new('probe')
print('MAT_HAS_NODE_TREE', m.node_tree is not None, hasattr(m, 'use_nodes'))
try:
    m.use_nodes = True
except Exception as e:
    print('use_nodes err', e)
print('MAT_NODES', [n.bl_idname for n in m.node_tree.nodes] if m.node_tree else None)
pr = [n for n in m.node_tree.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled']
if pr:
    print('PRINCIPLED_INPUTS', [i.name for i in pr[0].inputs])
for t in ('ShaderNodeTexNoise', 'ShaderNodeTexWave', 'ShaderNodeBump', 'ShaderNodeValToRGB', 'ShaderNodeMix', 'ShaderNodeAttribute', 'ShaderNodeEmission', 'ShaderNodeMapRange', 'ShaderNodeVectorMath', 'ShaderNodeTexGradient'):
    try:
        n = m.node_tree.nodes.new(t)
        print('NODE', t, 'IN', [i.name for i in n.inputs][:12], 'OUT', [o.name for o in n.outputs])
    except Exception as e:
        print('NODE_FAIL', t, e)
gpu = bpy.context.preferences.addons.get('cycles')
print('GPU_BACKEND', getattr(bpy.context.preferences.system, 'gpu_backend', None))
print('PROBE_DONE')
