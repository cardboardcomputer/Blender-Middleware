import os
import bpy
import krz

bl_info = {
    'name': 'Export Unity Lines (.lines)',
    'author': 'Cardboard Computer',
    'version': (0, 1),
    'blender': (2, 6, 8),
    'location': 'File > Import-Export > Unity Lines (.lines)',
    'description': 'Export loose edges of a mesh for Unity',
    'category': 'Cardboard',
}

class Color(object):
    def __init__(self, r, g, b, a):
        self.r = r
        self.g = g
        self.b = b
        self.a = a

    def __eq__(self, other):
        return (self.r, self.g, self.b, self.a) == other

    def __iter__(self):
        return iter((self.r, self.g, self.b, self.a))

class Vertex(object):
    def __init__(self, index, co, color, normal):
        self.index = index
        self.co = co
        self.color = color
        self.normal = normal

class Edge(object):
    def __init__(self, a, b):
        self.a = a
        self.b = b

class Line(object):
    def __init__(self, edge):
        self.vertices = [edge.a, edge.b]

    def is_connected(self, edge):
        head = self.vertices[0]
        tail = self.vertices[-1]
        return (head == edge.a or head == edge.b or
                tail == edge.a or tail == edge.b)

    def extend(self, edge):
        if self.is_connected(edge):
            a, b = edge.a, edge.b
            head = self.vertices[0]
            tail = self.vertices[-1]
            if a == head:
                self.vertices.insert(0, b)
            elif b == head:
                self.vertices.insert(0, a)
            elif a == tail:
                self.vertices.append(b)
            else:
                self.vertices.append(a)
            return True
        else:
            return False

    def consume(self, edges):
        consumed = -1
        remaining = list(edges)
        while consumed:
            consumed = 0
            for edge in list(remaining):
                if self.extend(edge):
                    consumed += 1
                    remaining.remove(edge)
        return remaining

def floats_to_strings(floats, precision=6):
    fmt = '%%.%if' % precision
    ret = map(lambda f: (fmt % f).rstrip('0').rstrip('.'), floats)
    ret = map(lambda s: '0' if s == '-0' else s, ret)
    return ret

def export_unity_lines(
    obj,
    filepath,
    precision=6,
    color_layer=''):

    export_colormap = krz.colors.Manager(obj).get_export_colormap()
    if export_colormap:
        map_size = export_colormap.get_size()
    else:
        map_size = 1
    bias = 1. / map_size * 0.5

    vertices = []
    edges = []
    lines = []

    if not color_layer:
        color_layer = krz.colors.Manager(obj).get_export_layer().name

    krz.legacy.upgrade_line_attributes(obj)
    mesh = obj.to_mesh(scene=bpy.context.scene, apply_modifiers=True, settings='PREVIEW')
    colors = krz.colors.layer(obj, color_layer)
    normals = krz.lines.normals(obj)

    (min_x, min_y, min_z) = (max_x, max_y, max_z) = mesh.vertices[0].co

    for i, v in enumerate(mesh.vertices):
        if v.co.x < min_x:
            min_x = v.co.x
        if v.co.x > max_x:
            max_x = v.co.x
        if v.co.y < min_y:
            min_y = v.co.y
        if v.co.y > max_y:
            max_y = v.co.y
        if v.co.z < min_z:
            min_z = v.co.z
        if v.co.z > max_z:
            max_z = v.co.z

        cd = colors.samples[v.index]
        color = Color(cd.color.r, cd.color.g, cd.color.b, cd.alpha)

        nd = normals.get(v.index)
        normal = (nd['X'], nd['Y'], nd['Z'])

        vertices.append(Vertex(i, v.co, color, normal))

    for edge in mesh.edges:
        a = vertices[edge.vertices[0]]
        b = vertices[edge.vertices[1]]
        edges.append(Edge(a, b))

    while edges:
        line = Line(edges.pop(0))
        edges = line.consume(edges)
        lines.append(line)

    with open(filepath, 'w') as fp:
        class_name = os.path.basename(filepath)[:-3]

        for i, vertex in enumerate(vertices):
            x, y, z = floats_to_strings((-vertex.co.x, vertex.co.y, vertex.co.z), precision)
            fp.write('%s %s %s' % (x, y, z))
            if i < len(vertices) - 1:
                fp.write(' ')
        fp.write('\n')

        for i, vertex in enumerate(vertices):
            r, g, b, a = floats_to_strings((vertex.color.r, vertex.color.g, vertex.color.b, vertex.color.a), precision)
            fp.write('%s %s %s %s' % (r, g, b, a))
            if i < len(vertices) - 1:
                fp.write(' ')
        fp.write('\n')

        if export_colormap:
            for i, vertex in enumerate(vertices):
                u = int(vertex.index % map_size) / map_size + bias
                v = int(vertex.index / map_size) / map_size + bias
                u, v = floats_to_strings((u, v), precision)
                fp.write('%s %s' % (u, v))
                if i < len(vertices) - 1:
                    fp.write(' ')
        else:
            fp.write(' '.join(['0'] * (len(vertices) * 2)))
        fp.write('\n')

        indices = []
        for line in lines:
            for i in range(len(line.vertices) - 1):
                indices.extend([line.vertices[i].index, line.vertices[i + 1].index])
        fp.write(' '.join(map(str, indices)))
        fp.write('\n')

        for i, vertex in enumerate(vertices):
            x, y, z = floats_to_strings((-vertex.normal[0], vertex.normal[1], vertex.normal[2]), precision)
            fp.write('%s %s %s' % (x, y, z))
            if i < len(vertices) - 1:
                fp.write(' ')

class UnityLineExporter(bpy.types.Operator):
    bl_idname = 'cc.export_unity_lines'
    bl_label = 'Export Unity Lines'

    filepath = bpy.props.StringProperty(
        subtype='FILE_PATH',)
    check_existing = bpy.props.BoolProperty(
        name="Check Existing",
        description="Check and warn on overwriting existing files",
        default=True,
        options={'HIDDEN'},)
    precision = bpy.props.IntProperty(
        name="Float Precision",
        description="Float precision used for GL commands",
        default=6)
    color_layer = bpy.props.StringProperty(
        name='Color Layer', default='')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH'

    def execute(self, context):
        export_unity_lines(
            context.active_object,
            self.filepath,
            self.precision,
            self.color_layer)
        return {'FINISHED'}

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = bpy.path.ensure_ext(bpy.data.filepath, ".lines")
        export_layer = krz.colors.Manager(context.active_object).get_export_layer()
        if export_layer:
            self.color_layer = export_layer.name

        path = os.path.dirname(self.filepath)
        blendname = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
        objname = context.active_object.name
        if objname.endswith('.Lines'):
            objname = objname[:-6]
        elif objname.endswith('Lines'):
            objname = objname[:-5]
        name = '%s%s' % (blendname, objname)
        filename = '%s.lines' % name
        self.filepath = os.path.join(path, filename)

        wm = context.window_manager
        wm.fileselect_add(self)
        return {'RUNNING_MODAL'}

def menu_import(self, context):
    self.layout.operator(UnityLineExporter.bl_idname, text="Unity Lines (.lines)")

def menu_export(self, context):
    self.layout.operator(UnityLineExporter.bl_idname, text="Unity Lines (.lines)")

def register():
    bpy.utils.register_module(__name__)

    bpy.types.INFO_MT_file_import.append(menu_import)
    bpy.types.INFO_MT_file_export.append(menu_export)

def unregister():
    bpy.utils.unregister_module(__name__)

    bpy.types.INFO_MT_file_import.remove(menu_import)
    bpy.types.INFO_MT_file_export.remove(menu_export)

if __name__ == "__main__":
    register()