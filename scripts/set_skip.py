"""Make the saved .blend skip frames that already exist (lets two render jobs share a frame range)."""
import bpy
s = bpy.context.scene
s.render.use_overwrite = False
s.render.use_placeholder = True
bpy.ops.wm.save_mainfile()
print('SKIP_SET', s.render.use_overwrite, s.render.use_placeholder)
