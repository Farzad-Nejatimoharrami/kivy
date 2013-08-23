#
# Kivy - Crossplatform NUI toolkit
# http://kivy.org/
#

import sys

from copy import deepcopy
import os
from os.path import join, dirname, sep, exists
from os import walk, environ
from distutils.core import setup
from distutils.extension import Extension

if sys.version > '3':
    PY3 = True
else:
    PY3 = False


# -----------------------------------------------------------------------------
# Determine on which platform we are

platform = sys.platform

# Detect Python for android project (http://github.com/kivy/python-for-android)
ndkplatform = environ.get('NDKPLATFORM')
if ndkplatform is not None and environ.get('LIBLINK'):
    platform = 'android'
kivy_ios_root = environ.get('KIVYIOSROOT', None)
if kivy_ios_root is not None:
    platform = 'ios'
if exists('/opt/vc/include/bcm_host.h'):
    platform = 'rpi'

# -----------------------------------------------------------------------------
# Detect options
#
c_options = {
    'use_rpi': platform == 'rpi',
    'use_opengl_es2': True,
    'use_opengl_debug': False,
    'use_glew': False,
    'use_sdl': False,
    'use_sdl2': False,
    'use_ios': False,
    'use_mesagl': False,
    'use_x11': False}

# now check if environ is changing the default values
for key in list(c_options.keys()):
    ukey = key.upper()
    if ukey in environ:
        value = bool(int(environ[ukey]))
        print('Environ change {0} -> {1}'.format(key, value))
        c_options[key] = value

# -----------------------------------------------------------------------------
# Cython check
# on python-for-android and kivy-ios, cython usage is external
have_cython = False
if platform in ('ios', 'android'):
    print('\nCython check avoided.')
else:
    try:
        # check for cython
        from Cython.Distutils import build_ext
        have_cython = True
    except ImportError:
        print('\nCython is missing, its required for compiling kivy !\n\n')
        raise

if not have_cython:
    from distutils.command.build_ext import build_ext


# -----------------------------------------------------------------------------
# Setup classes

class KivyBuildExt(build_ext):

    def build_extensions(self):
        print('Build configuration is:')
        for opt, value in c_options.items():
            print(' * {0} = {1}'.format(opt, value))
        print('Generate config.h')
        config_h = join(dirname(__file__), 'kivy', 'graphics', 'config.h')
        with open(config_h, 'w') as fd:
            fd.write('// Autogenerated file for Kivy C configuration\n')
            for k, v in c_options.items():
                fd.write('#define __{0} {1}\n'.format(k.upper(), int(v)))

        print('Generate config.pxi')
        config_pxi = join(dirname(__file__), 'kivy', 'graphics', 'config.pxi')
        with open(config_pxi, 'w') as fd:
            fd.write('# Autogenerated file for Kivy Cython configuration\n')
            for k, v in c_options.items():
                fd.write('DEF {0} = {1}\n'.format(k.upper(), int(v)))
            fd.write('DEF PY3 = {0}\n'.format(int(PY3)))

        build_ext.build_extensions(self)


# -----------------------------------------------------------------------------
# extract version (simulate doc generation, kivy will be not imported)
environ['KIVY_DOC_INCLUDE'] = '1'
import kivy

# extra build commands go in the cmdclass dict {'command-name': CommandClass}
# see tools.packaging.{platform}.build.py for custom build commands for
# portable packages.  also e.g. we use build_ext command from cython if its
# installed for c extensions.
from kivy.tools.packaging.factory import FactoryBuild
cmdclass = {
    'build_factory': FactoryBuild,
    'build_ext': KivyBuildExt}

try:
    # add build rules for portable packages to cmdclass
    if platform == 'win32':
        from kivy.tools.packaging.win32.build import WindowsPortableBuild
        cmdclass['build_portable'] = WindowsPortableBuild
    elif platform == 'darwin':
        from kivy.tools.packaging.osx.build import OSXPortableBuild
        cmdclass['build_portable'] = OSXPortableBuild
except ImportError:
    print('User distribution detected, avoid portable command.')

# Detect which opengl version headers to use
if platform in ('android', 'darwin', 'ios', 'rpi'):
    pass
elif platform == 'win32':
    print('Windows platform detected, force GLEW usage.')
    c_options['use_glew'] = True
else:
    # searching GLES headers
    default_header_dirs = ['/usr/include', '/usr/local/include']
    found = False
    for hdir in default_header_dirs:
        filename = join(hdir, 'GLES2', 'gl2.h')
        if exists(filename):
            found = True
            print('Found GLES 2.0 headers at {0}'.format(filename))
            break
    if not found:
        print('WARNING: GLES 2.0 headers are not found')
        print('Fallback to Desktop opengl headers.')
        c_options['use_opengl_es2'] = False

# check if we are in a kivy-ios build
if platform == 'ios':
    print('Kivy-IOS project environment detect, use it.')
    print('Kivy-IOS project located at {0}'.format(kivy_ios_root))
    print('Activate SDL compilation.')
    c_options['use_ios'] = True
    c_options['use_sdl'] = True

# -----------------------------------------------------------------------------
# declare flags

def get_modulename_from_file(filename):
    filename = filename.replace(sep, '/')
    pyx = '.'.join(filename.split('.')[:-1])
    pyxl = pyx.split('/')
    while pyxl[0] != 'kivy':
        pyxl.pop(0)
    if pyxl[1] == 'kivy':
        pyxl.pop(0)
    return '.'.join(pyxl)


class CythonExtension(Extension):

    def __init__(self, *args, **kwargs):
        Extension.__init__(self, *args, **kwargs)
        self.cython_directives = {
            'c_string_encoding': 'utf-8',
            'profile': 'USE_PROFILE' in environ,
            'embedsignature': 'USE_EMBEDSIGNATURE' in environ}
        # XXX with pip, setuptools is imported before distutils, and change
        # our pyx to c, then, cythonize doesn't happen. So force again our
        # sources
        self.sources = args[1]


def merge(d1, *args):
    d1 = deepcopy(d1)
    for d2 in args:
        for key, value in d2.items():
            value = deepcopy(value)
            if key in d1:
                d1[key].extend(value)
            else:
                d1[key] = value
    return d1

def determine_base_flags():
    flags = {
        'libraries': ['m'],
        'include_dirs': [],
        'extra_link_args': [],
        'extra_compile_args': []}
    if c_options['use_ios']:
        sysroot = environ.get('IOSSDKROOT', environ.get('SDKROOT'))
        if not sysroot:
            raise Exception('IOSSDKROOT is not set')
        flags['include_dirs'] += [sysroot]
        flags['extra_compile_args'] += ['-isysroot', sysroot]
        flags['extra_link_args'] += ['-isysroot', sysroot]
    elif platform == 'darwin':
        v = os.uname()
        if v[2] == '13.0.0':
    	    sysroot = '/Applications/Xcode5-DP.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX10.8.sdk/System/Library/Frameworks'
        else:
            sysroot = '/System/Library/Frameworks/ApplicationServices.framework/Frameworks'
        flags['extra_compile_args'] += ['-F%s' % sysroot]
        flags['extra_link_args'] += ['-F%s' % sysroot]
    return flags

def determine_gl_flags():
    flags = {'libraries': []}
    if platform == 'win32':
        flags['libraries'] = ['opengl32']
    elif platform == 'ios':
        flags['libraries'] = ['GLESv2']
        flags['extra_link_args'] = ['-framework', 'OpenGLES']
    elif platform == 'darwin':
        flags['extra_link_args'] = ['-framework', 'OpenGL', '-arch', 'x86_64']
        flags['extra_compile_args'] = ['-arch', 'x86_64']
    elif platform.startswith('freebsd'):
        flags['include_dirs'] = ['/usr/local/include']
        flags['extra_link_args'] = ['-L', '/usr/local/lib']
        flags['libraries'] = ['GL']
    elif platform.startswith('openbsd'):
        flags['include_dirs'] = ['/usr/X11R6/include']
        flags['extra_link_args'] = ['-L', '/usr/X11R6/lib']
        flags['libraries'] = ['GL']
    elif platform == 'android':
        flags['include_dirs'] = [join(ndkplatform, 'usr', 'include')]
        flags['extra_link_args'] = ['-L', join(ndkplatform, 'usr', 'lib')]
        flags['libraries'] = ['GLESv2']
    elif platform == 'rpi':
        flags['include_dirs'] = ['/opt/vc/include',
            '/opt/vc/include/interface/vcos/pthreads',
            '/opt/vc/include/interface/vmcs_host/linux']
        flags['extra_link_args'] = ['-L', '/opt/vc/lib']
        flags['libraries'] = ['GLESv2']
    else:
        flags['libraries'] = ['GL']
    if c_options['use_glew']:
        if platform == 'win32':
            flags['libraries'] += ['glew32']
        else:
            flags['libraries'] += ['GLEW']
    return flags

def determine_sdl():
    flags = {}
    if not c_options['use_sdl']:
        return flags

    flags['libraries'] = ['SDL', 'SDL_ttf', 'freetype', 'z', 'bz2']
    flags['include_dirs'] = []
    flags['extra_link_args'] = []
    flags['extra_compile_args'] = []

    # Paths as per homebrew (modified formula to use hg checkout)
    if c_options['use_ios']:
        # Note: on IOS, SDL is already loaded by the launcher/main.m
        # So if we add it here, it will just complain about duplicate
        # symbol, cause libSDL.a would be included in main.m binary +
        # text_sdlttf.so
        # At the result, we are linking without SDL explicitly, and add
        # -undefined dynamic_lookup
        # (/tito)
        flags['libraries'] = ['SDL_ttf', 'freetype', 'bz2']
        flags['include_dirs'] += [
            join(kivy_ios_root, 'build', 'include'),
            join(kivy_ios_root, 'build', 'include', 'SDL'),
            join(kivy_ios_root, 'build', 'include', 'freetype')]
        flags['extra_link_args'] += [
            '-L', join(kivy_ios_root, 'build', 'lib'),
            '-undefined', 'dynamic_lookup']
    else:
        flags['include_dirs'] = ['/usr/local/include/SDL']
        flags['extra_link_args'] += ['-L/usr/local/lib/']

    if platform == 'ios':
        flags['extra_link_args'] += [
            '-framework', 'Foundation',
            '-framework', 'UIKit',
            '-framework', 'AudioToolbox',
            '-framework', 'CoreGraphics',
            '-framework', 'QuartzCore',
            '-framework', 'MobileCoreServices',
            '-framework', 'ImageIO']
    elif platform == 'darwin':
        flags['extra_link_args'] += [
            '-framework', 'ApplicationServices']
    return flags

def determine_sdl2():
    flags = {}
    if not c_options['use_sdl2']:
        return flags

    flags['libraries'] = ['SDL2', 'SDL2_ttf', 'SDL2_image', 'SDL2_mixer']
    flags['include_dirs'] = ['/usr/local/include/SDL2', '/usr/include/SDL2']
    flags['extra_link_args'] = []
    flags['extra_compile_args'] = []
    flags['extra_link_args'] += ['-L/usr/local/lib/']

    # ensure headers for all the SDL2 and sub libraries are available
    libs_to_check = ['SDL', 'SDL_mixer', 'SDL_ttf', 'SDL_image']
    can_compile = True
    for lib in libs_to_check:
        found = False
        for d in flags['include_dirs']:
            fn = join(d, '{}.h'.format(lib))
            if exists(fn):
                found = True
                print 'SDL2: found {} header at {}'.format(lib, fn)
                break

        if not found:
            print 'SDL2: missing sub library {}'.format(lib)
            can_compile = False

    if not can_compile:
        c_options['use_sdl2'] = False
        return {}

    return flags

def determine_graphics_pxd():
    flags = {'depends': [join(dirname(__file__), 'kivy', x) for x in [
        'graphics/buffer.pxd',
        'graphics/c_opengl.pxd',
        'graphics/c_opengl_debug.pxd',
        'graphics/compiler.pxd',
        'graphics/context_instructions.pxd',
        'graphics/fbo.pxd',
        'graphics/instructions.pxd',
        'graphics/opengl_utils.pxd',
        'graphics/shader.pxd',
        'graphics/texture.pxd',
        'graphics/transformation.pxd',
        'graphics/vbo.pxd',
        'graphics/vertex.pxd']]}
    return flags

base_flags = determine_base_flags()
gl_flags = determine_gl_flags()
graphics_flags = determine_graphics_pxd()

# -----------------------------------------------------------------------------
# sources to compile
sources = {
    '_event.pyx': base_flags,
    'properties.pyx': base_flags,
    'graphics/buffer.pyx': base_flags,
    'graphics/context.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/c_opengl_debug.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/compiler.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/context_instructions.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/fbo.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/gl_instructions.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/instructions.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/opengl.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/opengl_utils.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/shader.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/stencil_instructions.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/texture.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/transformation.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/vbo.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/vertex.pyx': merge(
            base_flags, gl_flags, graphics_flags),
    'graphics/vertex_instructions.pyx': merge(
            base_flags, gl_flags, graphics_flags)}

if c_options['use_sdl']:
    sdl_flags = determine_sdl()
    sources['core/window/sdl.pyx'] = merge(
        base_flags, gl_flags, sdl_flags)
    sources['core/text/text_sdlttf.pyx'] = merge(
        base_flags, gl_flags, sdl_flags)
    sources['core/audio/audio_sdl.pyx'] = merge(
        base_flags, sdl_flags)

if c_options['use_sdl2']:
    sdl2_flags = determine_sdl2()
    if sdl2_flags:
        sources['core/window/_window_sdl2.pyx'] = merge(
            base_flags, gl_flags, sdl2_flags)
        sources['core/image/_img_sdl2.pyx'] = merge(
            base_flags, gl_flags, sdl2_flags)
        sources['core/text/_text_sdl2.pyx'] = merge(
            base_flags, gl_flags, sdl2_flags)

if platform in ('darwin', 'ios'):
    # activate ImageIO provider for our core image
    if platform == 'ios':
        osx_flags = {'extra_link_args': [
            '-framework', 'Foundation',
            '-framework', 'UIKit',
            '-framework', 'AudioToolbox',
            '-framework', 'CoreGraphics',
            '-framework', 'QuartzCore',
            '-framework', 'ImageIO']}
    else:
        osx_flags = {'extra_link_args': [
            '-framework', 'ApplicationServices']}
    sources['core/image/img_imageio.pyx'] = merge(
        base_flags, osx_flags)

if c_options['use_rpi']:
    sources['lib/vidcore_lite/egl.pyx'] = merge(
            base_flags, gl_flags)
    sources['lib/vidcore_lite/bcm.pyx'] = merge(
            base_flags, gl_flags)
    #sources['core/window/window_egl_rpi.pyx'] = merge(
    #        base_flags, gl_flags)

if c_options['use_x11']:
    sources['core/window/window_x11.pyx'] = merge(
        base_flags, gl_flags, graphics_flags, {
            'depends': [join(dirname(__file__),
                'kivy/core/window/window_x11_core.c')],
            'libraries': ['Xrender', 'X11', 'm']
        })


# -----------------------------------------------------------------------------
# extension modules

def get_extensions_from_sources(sources):
    ext_modules = []
    if environ.get('KIVY_FAKE_BUILDEXT'):
        print('Fake build_ext asked, will generate only .h/.c')
        return ext_modules
    for pyx, flags in sources.items():
        pyx = join(dirname(__file__), 'kivy', pyx)
        if not have_cython:
            pyx = '%s.c' % pyx[:-4]
            depends = []
        else:
            depends = flags.pop('depends', [])
        module_name = get_modulename_from_file(pyx)
        flags_clean = {}
        for key, value in flags.items():
            if len(value):
                flags_clean[key] = value
        ext_modules.append(CythonExtension(module_name,
            [pyx] + depends, **flags_clean))
    return ext_modules

ext_modules = get_extensions_from_sources(sources)

# -----------------------------------------------------------------------------
# automatically detect data files
data_file_prefix = 'share/kivy-'
examples = {}
examples_allowed_ext = ('readme', 'py', 'wav', 'png', 'jpg', 'svg', 'json',
                        'avi', 'gif', 'txt', 'ttf', 'obj', 'mtl', 'kv')
for root, subFolders, files in walk('examples'):
    for fn in files:
        ext = fn.split('.')[-1].lower()
        if ext not in examples_allowed_ext:
            continue
        filename = join(root, fn)
        directory = '%s%s' % (data_file_prefix, dirname(filename))
        if not directory in examples:
            examples[directory] = []
        examples[directory].append(filename)

# -----------------------------------------------------------------------------
# setup !
setup(
    name='Kivy',
    version=kivy.__version__,
    author='Kivy Crew',
    author_email='kivy-dev@googlegroups.com',
    url='http://kivy.org/',
    license='MIT',
    description=(
        'A software library for rapid development of '
        'hardware-accelerated multitouch applications.'),
    ext_modules=ext_modules,
    cmdclass=cmdclass,
    scripts=['kivy/tools/garden'],
    packages=[
        'kivy',
        'kivy.adapters',
        'kivy.core',
        'kivy.core.audio',
        'kivy.core.camera',
        'kivy.core.clipboard',
        'kivy.core.image',
        'kivy.core.gl',
        'kivy.core.spelling',
        'kivy.core.text',
        'kivy.core.video',
        'kivy.core.window',
        'kivy.effects',
        'kivy.ext',
        'kivy.graphics',
        'kivy.input',
        'kivy.input.postproc',
        'kivy.input.providers',
        'kivy.lib',
        'kivy.lib.osc',
        'kivy.lib.vidcore_lite',
        'kivy.modules',
        'kivy.network',
        'kivy.tools',
        'kivy.tools.packaging',
        'kivy.tools.packaging.pyinstaller_hooks',
        'kivy.tools.highlight',
        'kivy.extras',
        'kivy.tools.extensions',
        'kivy.uix', ],
    package_dir={'kivy': 'kivy'},
    package_data={'kivy': [
        'data/*.kv',
        'data/*.json',
        'data/fonts/*.ttf',
        'data/images/*.png',
        'data/images/*.jpg',
        'data/images/*.gif',
        'data/images/*.atlas',
        'data/keyboards/*.json',
        'data/logo/*.png',
        'data/glsl/*.png',
        'data/glsl/*.vs',
        'data/glsl/*.fs',
        'tools/highlight/*.vim',
        'tools/highlight/*.el',
        'tools/packaging/README.txt',
        'tools/packaging/win32/kivy.bat',
        'tools/packaging/win32/kivyenv.sh',
        'tools/packaging/win32/README.txt',
        'tools/packaging/osx/Info.plist',
        'tools/packaging/osx/InfoPlist.strings',
        'tools/packaging/osx/kivy.sh']},
    data_files=list(examples.items()),
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: MacOS X',
        'Environment :: Win32 (MS Windows)',
        'Environment :: X11 Applications',
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Information Technology',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: BSD :: FreeBSD',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Artistic Software',
        'Topic :: Games/Entertainment',
        'Topic :: Multimedia :: Graphics :: 3D Rendering',
        'Topic :: Multimedia :: Graphics :: Capture :: Digital Camera',
        'Topic :: Multimedia :: Graphics :: Presentation',
        'Topic :: Multimedia :: Graphics :: Viewers',
        'Topic :: Multimedia :: Sound/Audio :: Players :: MP3',
        'Topic :: Multimedia :: Video :: Display',
        'Topic :: Scientific/Engineering :: Human Machine Interfaces',
        'Topic :: Scientific/Engineering :: Visualization',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: User Interfaces'])

