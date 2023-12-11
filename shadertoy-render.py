#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (c) 2015, Alex J. Champandard
# Copyright (c) 2015, Jasmin Patry
# Copyright (c) 2015, Vispy Development Team.
# Distributed under the (new) BSD License.

# modified, 2018, Danil

from __future__ import unicode_literals, print_function

import argparse
import datetime
import math
import os.path
import os
import re
import subprocess
import sys
import time

import numpy

import vispy
from vispy import app
from vispy import gloo
from vispy import io
from vispy.gloo import gl
from vispy.gloo.util import _screenshot
from vispy.io import load_data_file, read_png
import vispy.util.keys as keys

import watchdog
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

ffmpeg_file="ffmpeg"

if os.name == 'nt':
    ffmpeg_file="C:/ffmpeg-2021-02-02-git-2367affc2c-full_build/bin/ffmpeg.exe"
    if(not os.path.exists(ffmpeg_file)):
      print("Error: file ffmpeg_file does not exist, edit line 41 of shadertoy-render.py")
      exit()

max_iChannels=6 # equal iChannelXX
max_iTextures=6 # equal iTextureXX

try:
  import imageio as iio
except ImportError:
  print("not using imageio")

try:
  import google.colab
  IN_COLAB = True
except:
  IN_COLAB = False

vertex = \
    """
attribute vec2 position;
void main()
{
    gl_Position = vec4(position, 0.0, 1.0);
}
"""

fragment_template = \
    """
uniform vec3      iResolution;           // viewport resolution (in pixels)
uniform float     iGlobalTime;           // shader playback time (in seconds)
uniform vec4      iMouse;                // mouse pixel coords
uniform vec4      iDate;                 // (year, month, day, time in seconds)
uniform float     iSampleRate;           // sound sample rate (i.e., 44100)
uniform sampler2D iChannel0;             // input channel
uniform sampler2D iChannel1;             // input channel
uniform sampler2D iChannel2;             // input channel
uniform sampler2D iChannel3;             // input channel
uniform sampler2D iChannel4;             // input channel
uniform sampler2D iChannel5;             // input channel
uniform sampler2D u_channel0;             // input channel
uniform sampler2D u_channel1;             // input channel
uniform sampler2D u_channel2;             // input channel
uniform sampler2D u_channel3;             // input channel
uniform sampler2D u_channel4;             // input channel
uniform sampler2D u_channel5;             // input channel
uniform sampler2D iTexture0;             // input channel
uniform sampler2D iTexture1;             // input channel
uniform sampler2D iTexture2;             // input channel
uniform sampler2D iTexture3;             // input channel
uniform sampler2D iTexture4;             // input channel
uniform sampler2D iTexture5;             // input channel
uniform vec3      iChannelResolution[6]; // channel resolution (in pixels)
uniform vec3      iTextureResolution[6]; // channel resolution (in pixels)
uniform float     iChannelTime[6];       // channel playback time (in sec)
uniform vec2      iOffset;               // pixel offset for tiled rendering
uniform int       iFrame; 
uniform float     iTimeDelta; 
#define iTime iGlobalTime

%s

void main()
{
    mainImage(gl_FragColor, gl_FragCoord.xy + iOffset);
}
"""

preamble_lines = fragment_template.split('\n').index('%s')

error_shader = \
    """
void mainImage( out vec4 fragColor, in vec2 fragCoord )
{
    discard;
}
"""


def error(msg):
    print('Error: ' + msg, file=sys.stderr)
    sys.exit(1)


def warn(msg):
    print('Warning: ' + msg, file=sys.stderr)


def noise(resolution=64, nchannels=1):
    size = (resolution, resolution, nchannels)
    return numpy.random.randint(low=0, high=256,
                                size=size).astype(numpy.uint8)


class RenderingCanvas(app.Canvas):

    def __init__(
        self,
        glsl,
        filename,
        interactive=True,
        output_size=None,
        render_size=None,
        position=None,
        start_time=0.,
        render_and_skip_frames=0,
        skip_frames_every_frame=0,
        cube_render = False,
        cube_final_render_size = None,
        interval='auto',
        duration=None,
        always_on_top=False,
        paused=False,
        output=None,
        progress_file=None,
        ffmpeg_pipe=None,
        ):

        app.Canvas.__init__(
            self,
            keys=('interactive' if interactive else None),
            size=(render_size if render_size else (cube_final_render_size if cube_render else output_size)),
            position=None,
            title=filename,
            always_on_top=always_on_top,
            show=False,
            resizable=ffmpeg_pipe is None,
            )

        self._filename = filename
        self._interactive = interactive
        self._output_size = output_size
        self._render_size = \
            (render_size if render_size else (cube_final_render_size if cube_render else output_size))
        self._output = output
        self._profile = False
        self._doubleFbo = True
        self._doubleFboid = 0
        self._doubleFboidLast = -1
        self._paused = paused
        self._timer = None
        self._start_time = start_time
        self._interval = interval
        self._ffmpeg_pipe = ffmpeg_pipe
        self._pre_render_iframe = 0
        self._skip_ef_render_iframe = 0
        self._total_to_pre_render_iframe = render_and_skip_frames
        self._total_to_skip_ef_render_iframe = skip_frames_every_frame
        self._cube_render = cube_render
        self._cube_final_render_size = cube_final_render_size

        # Determine number of frames to render

        if duration:
            assert interval != 'auto'
            self._render_frame_count = math.ceil(duration / interval)+self._total_to_pre_render_iframe+self._total_to_skip_ef_render_iframe*math.ceil(duration / interval)
        elif not interactive:
            self._render_frame_count = 1
        else:
            self._render_frame_count = None

        self._render_frame_index = 0

        clock = time.perf_counter()
        self._clock_time_zero = clock - start_time
        self._clock_time_start = clock

        if position is not None:
            self.position = position
            
        self.set_BufX()
        self.init_BufX()
        self.set_Buf_channel_input()
        # Initialize with a "known good" shader program, so that we can set all
        # the inputs once against it.

        self.program = gloo.Program(vertex, fragment_template
                                    % error_shader)
        self.program['position'] = [
            (-1, -1),
            (-1, 1),
            (1, 1),
            (-1, -1),
            (1, 1),
            (1, -1),
            ]
        self.program['iMouse'] = (0., 0., 0., 0.)
        self.program['iSampleRate'] = 44100.0
        self.program['iTimeDelta'] = self._interval
        self.program['iGlobalTime'] = start_time
        self.program['iFrame'] = self._render_frame_index
        self.program['iOffset'] = (0., 0.)

        self.activate_zoom()

        self.set_Buf_uniform('position' , [
            (-1, -1),
            (-1, 1),
            (1, 1),
            (-1, -1),
            (1, 1),
            (1, -1),
            ])
        self.set_Buf_uniform('iMouse' , (0., 0., 0., 0.))
        self.set_Buf_uniform('iSampleRate' , 44100.0)
        self.set_Buf_uniform('iFrame' , self._render_frame_index)
        self.set_Buf_uniform('iGlobalTime' , start_time)
        self.set_Buf_uniform('iOffset' , (0., 0.))
        self.set_Buf_uniform('iResolution' , (self._output_size[0],
                    self._output_size[1], 0.))
        self.set_Buf_uniform('iTimeDelta' , self._interval)
        
        video_path_prefix = "video_frames_"
        for x in range(0,max_iTextures):
            tfile_name = str(x)+'.png'
            if(os.path.exists(video_path_prefix+str(x))):
                tfile_name = video_path_prefix+str(x)+os.sep+str(self._render_frame_index+1)+'.png'
            try:
                try:
                  try:
                      self.set_texture_input(iio.v2.imread(tfile_name), i=x)
                      self.set_Buf_texture_input(iio.v2.imread(tfile_name), i=x)
                  except AttributeError:
                      self.set_texture_input(iio.imread(tfile_name), i=x)
                      self.set_Buf_texture_input(iio.imread(tfile_name), i=x)
                except NameError:
                  self.set_texture_input(read_png(tfile_name), i=x)
                  self.set_Buf_texture_input(read_png(tfile_name), i=x)
            except FileNotFoundError:
                self.set_texture_input(noise(resolution=2, nchannels=3), i=x)
                self.set_Buf_texture_input(noise(resolution=2, nchannels=3), i=x)
        
        self.set_channel_input()
        self.set_shader(glsl)

        if interactive:
            if not paused:
                self.ensure_timer()
            self.show()
        else:
            self._tile_index = 0
            self._tile_count = ((self._cube_final_render_size if self._cube_render else self._output_size)[0] + render_size[0] - 1) \
                // render_size[0] * (((self._cube_final_render_size if self._cube_render else self._output_size)[1] + render_size[1]
                    - 1) // render_size[1])
            self._tile_coord = [0, 0]
            self._progress_file = progress_file

            # Note that gloo.Texture2D and gloo.RenderBuffer use the numpy convention for dimensions ('shape'),
            # i.e., HxW
            
            self._rendertex = gloo.Texture2D(shape=render_size[::-1]
                    + (4, ))
            self._fbo = gloo.FrameBuffer(self._rendertex,
                    gloo.RenderBuffer(shape=render_size[::-1]))

            # Allocate buffer to hold final image

            self._img = numpy.zeros(shape=(self._cube_final_render_size if self._cube_render else self._output_size)[::-1] + (4,
                                    ), dtype=numpy.uint8)

            # Write progress file now so we'll know right away if there are any problems writing to it

            if self._progress_file:
                self.write_img(self._img, self._progress_file)

            self.program['iResolution'] = (self._cube_final_render_size if self._cube_render else self._output_size) + (0., )
            self.ensure_timer()
            
            

    def set_BufX(self):
        self._bufXused = []
        self._bufXglsl = []
        self._common_file = ''
        try:
          self._common_file = open('Common.glsl', 'r').read().encode('ascii', errors='ignore').decode()
        except FileNotFoundError:
          print('Common.glsl file not used')
        for i in range(max_iChannels):
            try:
                self._bufXglsl.append(self._common_file +'\n'+open('Buf%d.glsl' % i, 'r').read().encode('ascii', errors='ignore').decode())
                self._bufXused.append(True)
            except FileNotFoundError:
                print('FIle not found, used empty shader instead'+(' Buf%d.glsl' % i) + " used placeholder 64x64 render size")
                self._bufXglsl.append(self._common_file +'\n'+error_shader)
                self._bufXused.append(False)
                continue
        
    def set_Buf_uniform(self, uni, val):
        for i in range(max_iChannels):
            self._BufX[i][uni] = val
        
    def set_Buf_texture_input(self, img, i=0, rep=True):
        tex = gloo.Texture2D(img)
        tex.interpolation = 'linear'
        tex.wrapping = 'repeat' if rep else 'clamp_to_edge'
        for j in range(max_iTextures):
            self._BufX[j]['iTexture%d' % i] = tex
            self._BufX[j]['iTextureResolution[%d]' % i] = img.shape

    def set_Buf_channel_input(self):
        for i in range(max_iChannels):
            for j in range(max_iChannels):
                self._BufX[i]['iChannel%d' % j] =  self._texX[self._doubleFboid -1 if j>=i else self._doubleFboid][j]
                self._BufX[i]['u_channel%d' % j] = self._texX[self._doubleFboid -1 if j>=i else self._doubleFboid][j]
                self._BufX[i]['iChannelResolution[%d]' % j] =  self._output_size + (0., )

    def init_BufX(self):
        # Create texture to render to
        # Create FBO, attach the color buffer and depth buffer
        self._texX=[]
        self._fboX=[]
        self._BufX=[]
        self._texX.append([])
        self._fboX.append([])
        self._texX.append([])
        self._fboX.append([])
        for i in range(max_iChannels):
            self._texX[0].append(gloo.Texture2D(shape=self._output_size[::-1]
                    + (4, )if self._bufXused[i] else (64,64,4), format= 'rgba', interpolation='linear',wrapping = 'clamp_to_edge', internalformat = 'rgba32f'))
            self._fboX[0].append(gloo.FrameBuffer(self._texX[0][i],
                    gloo.RenderBuffer(shape=self._output_size[::-1]if self._bufXused[i] else (64,64))))
            self._texX[1].append(gloo.Texture2D(shape=self._output_size[::-1]
                    + (4, )if self._bufXused[i] else (64,64,4), format= 'rgba', interpolation='linear',wrapping = 'clamp_to_edge', internalformat = 'rgba32f'))
            self._fboX[1].append(gloo.FrameBuffer(self._texX[1][i],
                    gloo.RenderBuffer(shape=self._output_size[::-1]if self._bufXused[i] else (64,64))))
            self._BufX.append(gloo.Program(vertex, fragment_template
                                    % error_shader))


    def set_texture_input(self, img, i=0, rep=True):
        tex = gloo.Texture2D(img)
        tex.interpolation = 'linear'
        tex.wrapping = 'repeat' if rep else 'clamp_to_edge'
        self.program['iTexture%d' % i] = tex
        self.program['iTextureResolution[%d]' % i] = img.shape
        
    def set_channel_input(self):
        for i in range(max_iChannels):
            self.program['iChannel%d' % i] = self._texX[self._doubleFboid][i]
            self.program['u_channel%d' % i] = self._texX[self._doubleFboid][i]
            self.program['iChannelResolution[%d]' % i] =  self._output_size + (0., )

    def set_shader(self, glsl):
        self._glsl = self._common_file + '\n' + glsl

    def advance_time(self):
        if not self._paused:
            if self._interval == 'auto':
                self.program['iGlobalTime'] = time.perf_counter() \
                    - self._clock_time_zero
                for i in range(max_iChannels):
                    self._BufX[i]['iGlobalTime'] = self.program['iGlobalTime']
            else:
                self.program['iGlobalTime'] += self._interval
                for i in range(max_iChannels):
                    self._BufX[i]['iGlobalTime'] = self.program['iGlobalTime']

    def write_video_frame(self, img):
        if img.shape[0] != (self._cube_final_render_size[1] if self._cube_render else self._output_size[1]) or img.shape[1] \
            != (self._cube_final_render_size[0] if self._cube_render else self._output_size[0]):
            warn('Frame data is wrong size! Video will be corrupted.')

        self._ffmpeg_pipe.write(img.tobytes())

    def draw(self):
        for i in range(max_iChannels):
            if self._bufXglsl[i]:
                fragment = fragment_template % self._bufXglsl[i]
                self._bufXglsl[i] = None
                frag_handle = gl.glCreateShader(gl.GL_FRAGMENT_SHADER)
                gl.glShaderSource(frag_handle, fragment)
                gl.glCompileShader(frag_handle)
                status = gl.glGetShaderParameter(frag_handle,
                                        gl.GL_COMPILE_STATUS)
                if not status:
                    errors = gl.glGetShaderInfoLog(frag_handle)
                    errors = self.process_errors(errors)
                    print('Shader failed to compile:', file=sys.stderr)
                    print(errors, file=sys.stderr)
                    exit(1)
                else:
                    self._BufX[i].set_shaders(vertex, fragment)
                gl.glDeleteShader(frag_handle)
            
        if self._glsl:
            fragment = fragment_template % self._glsl
            self._glsl = None

            # Check to see if the shader will compile successfully before we
            # set it. We do this here because the ShaderWatcher runs in a
            # different thread and so can't access the GL context.

            frag_handle = gl.glCreateShader(gl.GL_FRAGMENT_SHADER)
            gl.glShaderSource(frag_handle, fragment)
            gl.glCompileShader(frag_handle)
            status = gl.glGetShaderParameter(frag_handle,
                    gl.GL_COMPILE_STATUS)
            if not status:
                errors = gl.glGetShaderInfoLog(frag_handle)
                errors = self.process_errors(errors)
                print('Shader failed to compile:', file=sys.stderr)
                print(errors, file=sys.stderr)
                exit(1)
                
                # Switch to error shader

                self._glsl = error_shader
                self.update()
            else:
                self.program.set_shaders(vertex, fragment)
            gl.glDeleteShader(frag_handle)

        if self._interactive:
            for i in range(max_iChannels):
                with self._fboX[self._doubleFboid][i]:
                    gloo.set_clear_color((0.0, 0.0, 0.0, 0.0))
                    gloo.clear(color=False, depth=True)
                    gloo.set_viewport(0, 0, *self._output_size)
                    self._BufX[i].draw()
            
            self.program.draw()

            if self._ffmpeg_pipe is not None:
                img = _screenshot()
                self.write_video_frame(img)

            self._render_frame_index += 1
            if self._render_frame_count is not None \
                and self._render_frame_index \
                >= self._render_frame_count:
                app.quit()
                return

            self._doubleFbo = not self._doubleFbo
            self._doubleFboid=(0 if self._doubleFbo else 1)
            self.advance_time()
            self.program['iFrame'] = self._render_frame_index
            self.set_Buf_uniform('iFrame' , self._render_frame_index)
            self.set_Buf_uniform('iMouse' , self.program['iMouse'])
            self.program['iMouse']=(self.program['iMouse'][0],self.program['iMouse'][1],self.program['iMouse'][2],-abs(self.program['iMouse'][3]))
            self.set_channel_input()
            self.set_Buf_channel_input()
        else:
            if(self._doubleFboidLast!=self._render_frame_index):
              self._doubleFboidLast=self._render_frame_index
              for i in range(max_iChannels):
                  with self._fboX[self._doubleFboid][i]:
                      gloo.set_clear_color((0.0, 0.0, 0.0, 0.0))
                      gloo.clear(color=False, depth=True)
                      gloo.set_viewport(0, 0, *self._output_size)
                      self._BufX[i].draw()
                    
            with self._fbo:
                rs = list(self._render_size)

                if self._tile_coord[0] + rs[0] > (self._cube_final_render_size if self._cube_render else self._output_size)[0]:
                    rs[0] = (self._cube_final_render_size if self._cube_render else self._output_size)[0] - self._tile_coord[0]

                if self._tile_coord[1] + rs[1] > (self._cube_final_render_size if self._cube_render else self._output_size)[1]:
                    rs[1] = (self._cube_final_render_size if self._cube_render else self._output_size)[1] - self._tile_coord[1]

                gloo.set_viewport(0, 0, *rs)
                self.program['iOffset'] = self._tile_coord
                self.program.draw()
                
                img = _screenshot()
                row = (self._cube_final_render_size if self._cube_render else self._output_size)[1] - self._tile_coord[1] - rs[1]
                col = self._tile_coord[0]
                self._img[row:row + rs[1], col:col + rs[0], :] = img
                

    def on_draw(self, event):
        self.draw()

    def on_mouse_press(self, event):
        (x, y) = event.pos
        imouse = (x, self.size[1] - y)
        imouse += imouse
        self.program['iMouse'] = imouse
        if not self._timer:
            self.update()
            
    def on_mouse_release(self, event):
        self.program['iMouse']=(self.program['iMouse'][0],self.program['iMouse'][1],-abs(self.program['iMouse'][2]),-abs(self.program['iMouse'][3]))
    
    def on_mouse_move(self, event):
        if event.is_dragging:
            (x, y) = event.pos
            (px, py) = event.press_event.pos
            imouse = (x, self.size[1] - y, px, self.size[1] - py)
            self.program['iMouse'] = imouse
            self.program['iMouse']=(self.program['iMouse'][0],self.program['iMouse'][1],self.program['iMouse'][2],-abs(self.program['iMouse'][3]))
            if not self._timer:
                self.update()

    def on_key_press(self, event):
        if event.key == 'q':
            self.show(False, False)
            self.app.quit()
            return
        elif event.key == 'p' or event.key == ' ':
            self._paused = not self._paused
            self.update_timer_state()
        elif event.key == 's':
            img = _screenshot()
            self.write_img(img)
        elif event.key == 'a':
            print('Size/pos args: --size %dx%d --pos %d,%d'
                  % (self.physical_size[0], self.physical_size[1],
                  self.position[0], self.position[1]))
        elif event.key == 'f':
            self._profile = not self._profile
            if self._profile:

                def print_profile(fps):
                    print('%.2f ms/frame' % (1000.0 / float(fps)))
                    return False

                self.measure_fps(1.0, print_profile)
            else:
                self.measure_fps(1.0, False)
            self.update_timer_state()
        elif event.key == keys.LEFT or event.key == keys.RIGHT:

            self._paused = True
            self.update_timer_state()
            step = 1.0 / 60.0
            if keys.ALT in event.modifiers:
                step *= 0.1
                if keys.SHIFT in event.modifiers:
                    step *= 0.1
            else:
                if keys.SHIFT in event.modifiers:
                    step *= 10.0
                if keys.CONTROL in event.modifiers:
                    step *= 100.0

            if event.key == keys.LEFT:
                step *= -1.0

            self.program['iGlobalTime'] += step

            self.print_t()

            self.update()

    def on_timer(self, event):
        if self._interactive:
            self.update()
        else:

            # update() doesn't call on_draw() if window is hidden under some toolkits,
            # so call draw() directly

            if self._render_frame_index==0:
                clock = time.perf_counter()
                self._clock_time_zero = time.perf_counter() - self._start_time
                self._clock_time_start = time.perf_counter()
                
            self.draw()

            # update tiles

            self._tile_index += 1

            clock_time_elapsed = time.perf_counter() - self._clock_time_start
            rendered_tile_count = self._tile_index \
                + self._render_frame_index * self._tile_count
            total_tile_count = self._tile_count \
                * self._render_frame_count
            clock_time_per_tile = clock_time_elapsed \
                / float(rendered_tile_count)
            clock_time_total = clock_time_per_tile * total_tile_count
            clock_time_remain = clock_time_total - clock_time_elapsed

            bar_length = 10
            bar_length_unit_value = (total_tile_count / bar_length)
            completed_bar_part = math.ceil(rendered_tile_count / bar_length_unit_value)
            progress = "*" * completed_bar_part
            remaining = " " * (bar_length - completed_bar_part)
            skip_frames_ctr = ""
            if(self._total_to_pre_render_iframe>0):
              skip_frames_ctr+=" s|%d/%d|" % (self._pre_render_iframe, self._total_to_pre_render_iframe)
            if(self._total_to_skip_ef_render_iframe>0):
              skip_frames_ctr+=" ef|%d/%d|" % (self._skip_ef_render_iframe, self._total_to_skip_ef_render_iframe)
            print(f'Tile %d / %d [{progress}{remaining}] (%.2f%%); %s elapsed; %s remaining; %s total'
                   % (
                rendered_tile_count,
                total_tile_count,
                rendered_tile_count * 100.0 / total_tile_count,
                str(datetime.timedelta(seconds=round(clock_time_elapsed))),
                str(datetime.timedelta(seconds=round(clock_time_remain))),
                str(datetime.timedelta(seconds=round(clock_time_total))),
                ) + skip_frames_ctr) #, end='\r')
            if self._tile_index == self._tile_count:
                if self._ffmpeg_pipe:
                    if(self._pre_render_iframe>=self._total_to_pre_render_iframe):
                      if(self._skip_ef_render_iframe>=self._total_to_skip_ef_render_iframe):
                        self.write_video_frame(self._img)
                    self._render_frame_index += 1
                    self._doubleFbo = not self._doubleFbo
                    self._doubleFboid=(0 if self._doubleFbo else 1)
                    self.program['iFrame'] = self._render_frame_index
                    self.set_Buf_uniform('iFrame' , self._render_frame_index)
                    self.set_channel_input()
                    self.set_Buf_channel_input()

                    if self._render_frame_count is not None \
                        and self._render_frame_index \
                        >= self._render_frame_count:
                        app.quit()
                        return

                    # Reset tile indices

                    self._tile_index = 0
                    self._tile_coord = [0, 0]

                    if(self._pre_render_iframe>=self._total_to_pre_render_iframe):
                      if(self._skip_ef_render_iframe>=self._total_to_skip_ef_render_iframe):
                        self.advance_time()
                        self._skip_ef_render_iframe=0
                      else:
                        self._skip_ef_render_iframe+=1
                    else:
                      self._pre_render_iframe+=1
                    
                    # video recording
                    # ---------------------
                    video_path_prefix = "video_frames_"
                    for x in range(0,max_iTextures):
                        if(os.path.exists(video_path_prefix+str(x))):
                            try:
                                try:
                                    timg = iio.v2.imread(video_path_prefix+str(x)+os.sep+str(self._render_frame_index+1)+'.png')
                                except AttributeError:
                                    timg = iio.imread(video_path_prefix+str(x)+os.sep+str(self._render_frame_index+1)+'.png')
                                self.set_texture_input(timg, i=x)
                                self.set_Buf_texture_input(timg, i=x)
                            except FileNotFoundError:
                                pass
                            except NameError:
                                print("NO video recording, video recording works only when imageio installed, pip install imageio")
                    # ---------------------
                    
                else:
                    self.write_img(self._img, self._output)
                    app.quit()
                    return
            else:
                self._tile_coord[0] += self._render_size[0]
                if self._tile_coord[0] >= (self._cube_final_render_size if self._cube_render else self._output_size)[0]:
                    self._tile_coord[0] = 0
                    self._tile_coord[1] += self._render_size[1]
                    if self._progress_file:
                        self.write_img(self._img, self._progress_file)

    def on_resize(self, event):
        self.activate_zoom()

    def activate_zoom(self):
        if hasattr(self, "_interactive") and self._interactive:
            gloo.set_viewport(0, 0, *self.physical_size)
            self.program['iResolution'] = (self.physical_size[0],
                    self.physical_size[1], 0.)

    def process_errors(self, errors):

        # NOTE (jasminp) Error message format depends on driver. Does this catch them all?

        lp = [re.compile(r'.*?0:(\d+): (.*)'),
              re.compile(r'0\((\d+)\) :[^:]*: (.*)')]  # intel/win
                                                       # nvidia/win

        linesOut = []
        for line in errors.split('\n'):
            result = None
            for p in lp:
                result = p.match(line)
                if result:
                    linesOut.append('%s(%d): error: %s'
                                    % (self._filename,
                                    int(result.group(1))
                                    - preamble_lines, result.group(2)))
                    break
            if not result:
                linesOut.append(line)
        return '\n'.join(linesOut)

    def print_t(self):
        print('t=%f' % self.program['iGlobalTime'])

    def ensure_timer(self):
        if not self._timer:
            self._timer = app.Timer(('auto'
                                     if self._ffmpeg_pipe else self._interval),
                                    connect=self.on_timer, start=True)

    def update_timer_state(self):
        if not self._paused:
            self._clock_time_zero = time.perf_counter() \
                - self.program['iGlobalTime']
            self.ensure_timer()
        else:
            if self._profile:
                self.ensure_timer()
            else:
                if self._timer:
                    self._timer.stop()
                    self._timer = None

            self.print_t()

    def write_img(self, img, filename=None):
        if filename is None:
            suffix = 0
            filepat = 'screen%d.png'
            while os.path.exists(filepat % suffix):
                suffix = suffix + 1
            filename = filepat % suffix
        io.write_png(filename, img)
        print('Wrote ' + filename)


class ShaderWatcher(FileSystemEventHandler):

    def __init__(self, filename, canvas):
        FileSystemEventHandler.__init__(self)
        self._filename = filename
        self._canvas = canvas

    def on_modified(self, event):
        if os.path.abspath(event.src_path) == self._filename:
            print('Updating shader...')

            glsl_shader = open(self._filename, 'r').read().encode('ascii', errors='ignore').decode()

            self._canvas.set_shader(glsl_shader)
            self._canvas.update()


if __name__ == '__main__':
    vispy.set_log_level('WARNING')

    parser = \
        argparse.ArgumentParser(description='Render a ShaderToy-style shader from the specified file.'
                                )
    parser.add_argument('input', type=str,
                        help='Source shader file to load from disk.')
    parser.add_argument('--size', type=str, default='1280x720',
                        help='Width and height of the viewport/output, e.g. 1920x1080 (string).'
                        )
    parser.add_argument('--bitrate', type=str, default='5M',
                        help='bitrate of video 1M 2M 15M etc'
                        )
    parser.add_argument('--pos', type=str,
                        help='Position of the viewport, e.g. 100,100 (string).'
                        )
    parser.add_argument('--time', type=float, default=0.,
                        help='Initial time value.')
    parser.add_argument('--rate', type=int, default=None,
                        help='Number of frames per second to render, e.g. 60 (int).'
                        )
    parser.add_argument('--duration', type=float, default=None,
                        help='Total seconds of video to encode, e.g. 30.0 (float).'
                        )
    parser.add_argument('--top', action='store_true',
                        help='Keep window on top.')
    parser.add_argument('--pause', action='store_true',
                        help='Start paused.')
    parser.add_argument('--tile-size', type=int, default=None,
                        help='Tile size for tiled rendering, e.g. 256 (int).'
                        )
    parser.add_argument('--progress-file', type=str,
                        help='Save tiled rendering progress to specified PNG file.'
                        )
    parser.add_argument('--output', type=str, default=None,
                        help='Render directly to the specified PNG or MP4/MOV/WEBM file. '

                        + 'Rendering is offscreen unless --interactive is specified.'
                        )
    parser.add_argument('--interactive', action='store_true',
                        help='Render interactively. This is the default unless --output is specified.'
                        )
    parser.add_argument('--verbose', default=False, action='store_true'
                        ,
                        help='Call subprocess with a high logging level.'
                        )
    parser.add_argument('--render_and_skip_frames', type=int, default=0,
                        help='Number of frames to skip(render but not recrod), 0 is no skip(default) (int). \n iTime is 0 on all skipped frames, BUT iFrame will process/count skipped frames.'
                        )
    parser.add_argument('--skip_frames_every_frame', type=int, default=0,
                        help='Skip Number of frames every frame. (for TAA etc)'
                        )
    parser.add_argument('--panorama_rec_size', type=str, default=None,
                        help='Cubemap final video size, e.g. 1920x1080 (string). When set - --size used as cube side size.'
    )
    parser.add_argument('--vispy_use', type=str, default='',
                        help='vispy.use - egl'
                        )

    args = parser.parse_args()
    
    # GLFW not part of anaconda python distro; works fine with default (PyQt4)

    try:
        if(len(args.vispy_use)>2):
          vispy.use(args.vispy_use)
        else:
          if(IN_COLAB):
            vispy.use('egl')
          else:
            vispy.use(app='Glfw', gl="gl+")
    except RuntimeError as e:
        pass

    resolution = tuple(int(i) for i in args.size.split('x'))
    cube_final_render_size = None
    if(args.panorama_rec_size):
      cube_final_render_size = tuple(int(i) for i in args.panorama_rec_size.split('x'))
    position = (tuple(int(i) for i in args.pos.split(',')) if args.pos
                is not None else None)

    output_to_video = False

    if args.output:
        (filename, file_ext) = os.path.splitext(args.output)
        file_ext = file_ext.lower()
        if file_ext == '.webm' or file_ext == '.mov' or file_ext \
            == '.mp4' or file_ext == '.mkv':
            output_to_video = True
        elif file_ext != '.png':
            error('output file must be either PNG or MP4/MOV/WEBM file.'
                  )

        if args.interactive and args.tile_size:
            error('--interactive is incompatible with --tile-size.')

        if output_to_video:
            if not args.duration and not args.interactive:
                error('Must specify --duration for non-interactive video renderinng.'
                      )

            if args.pause:
                error('--pause may not be specified when rendering to video.'
                      )
        else:

            if args.interactive:
                error('--interactive may not be specified for PNG output files.'
                      )

            if args.duration:
                error('--duration may not be specified for PNG output files.'
                      )
    else:

        args.interactive = True

    if args.rate is None and (output_to_video or args.duration):
        args.rate = 30

    if args.rate is None or args.rate <= 0.:
        if output_to_video:
            error('invalid --rate argument (%d).' % args.rate)
        else:
            interval = 'auto'
    else:
        interval = 1.0 / float(args.rate)

    filepath = os.path.abspath(args.input)
    glsl_shader = open(args.input, 'r').read().encode('ascii', errors='ignore').decode()

    observer = None
    ffmpeg = None
    ffmpeg_pipe = None

    if output_to_video:
        if file_ext == '.mov':
            ffmpeg = subprocess.Popen((
                ffmpeg_file,
                '-loglevel', ('verbose' if args.verbose else 'panic'),
                '-r', '%d' % args.rate,
                '-f', 'rawvideo',
                '-threads', '4',
                '-pix_fmt', 'rgba',
                '-s', args.panorama_rec_size if args.panorama_rec_size!=None else args.size,
                '-i', '-',
                '-c:v', 'qtrle',
                '-y', args.output,
                ), stdin=subprocess.PIPE)
        else:
            if file_ext == '.webm':
                ffmpeg = subprocess.Popen((
                    ffmpeg_file,
                    '-loglevel', ('verbose' if args.verbose else 'panic'),
                    '-r', '%d' % args.rate,
                    '-f', 'rawvideo',
                    '-threads', '4',
                    '-speed', '0',
                    '-pix_fmt', 'rgba',
                    '-s', args.panorama_rec_size if args.panorama_rec_size!=None else args.size,
                    '-i', '-',
                    '-c:v', 'vp8',
                    '-auto-alt-ref', '0',
                    '-b:v', args.bitrate,
                    '-crf', '10',
                    '-y', args.output,
                    ), stdin=subprocess.PIPE)
            else:
                ffmpeg = subprocess.Popen((
                    ffmpeg_file,
                    '-threads', '0',
                    '-loglevel', ('verbose' if args.verbose else 'panic'),
                    '-r', '%d' % args.rate,
                    '-f', 'rawvideo',
                    '-pix_fmt', 'rgba',
                    '-s', args.panorama_rec_size if args.panorama_rec_size!=None else args.size,
                    '-i', '-',
                    '-pix_fmt', 'yuv420p',
                    '-movflags', '+faststart',
                    '-b:v', args.bitrate,
                    '-preset', 'slow',
                    '-c:v', 'libx264',  # 'libx264', h264_nvenc
                    '-y', args.output,
                    ), stdin=subprocess.PIPE)
    ffmpeg_pipe = ffmpeg.stdin

    canvas = RenderingCanvas(
        glsl_shader,
        args.input,
        interactive=args.interactive,
        output_size=resolution,
        render_size=((args.tile_size, )
                     * 2 if args.tile_size else (cube_final_render_size if args.panorama_rec_size!=None else resolution)),
        position=position,
        start_time=args.time,
        
        render_and_skip_frames=args.render_and_skip_frames,
        skip_frames_every_frame=args.skip_frames_every_frame,
        cube_render = args.panorama_rec_size!=None,
        cube_final_render_size = cube_final_render_size,
        
        interval=interval,
        duration=args.duration,
        always_on_top=args.top,
        paused=args.pause,
        output=args.output,
        progress_file=args.progress_file,
        ffmpeg_pipe=ffmpeg_pipe,
        )

    if not args.output:
        observer = Observer()
        observer.schedule(ShaderWatcher(filepath, canvas),
                          os.path.dirname(filepath))
        observer.start()

    try:
        canvas.app.run()
    except KeyboardInterrupt:
        pass
    print("\n\n\n")
    
    if ffmpeg:
        ffmpeg.stdin.close()
        ffmpeg.wait()

    if observer:
        observer.stop()
        observer.join()
