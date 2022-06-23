shadertoy-render
================

**What is it**: creating video from shaders on Shadertoy. Fork from `original <https://github.com/alexjc/shadertoy-render>`_, source code edited.

**Uploading created video to Twitter/Instagram** - pixel format set to *yuv420p* for *libx264* codec and video can be uploaded to any social platform without problems.

Nor supported - Cubemaps, Shader-Cubemap, 3d texture, audio and video input also not supported.

**Update 2022:**
-----------------

``--tile-size=512`` command line argument to enable **tile rendering** (just add it to any render command) - useful when you want render very slow shader for 4k video, or you have very slow GPU. Also useful for Windows OS to avoid driver crash when frames rendered for longer than 2 sec.

*Frames will be rendered in small tiles(set size) per frame so it will load GPU much less than rendering full frame at once.*

**Tile rendering works only on Image shader** (*main_image.glsl* file). Buffers (A-D) still rendered full frame at once. Look commit `d0cd63 <https://github.com/danilw/shadertoy-to-video-with-FBO/commit/d0cd634c117dbf9083ce37df50f0bdfea1f09cb2>`_.

*discard* (shaders) - now works in buffers and Image shaders, all shaders support discard correcrly. But discard will be broken in Image shader (*main_image.glsl* file) when used with `--tile-size` option, so **do not use discard in Image when used tile rendering**.

**Update 2021:**
-----------------

Added Windows OS support instruction, **how to launch it on Windows OS** scroll down.

Added correct test for buffers queue *example_shadertoy_fbo*.

TODO - il develop better "shader recorder" using Vulkan and implementing all missing featres (audio/video/cubemaps/etc). That will be completely new project, this project is done.

**Look for useful ffmpeg commands below.** (also method of saving single frame(png with alpha) described there)


**Changes from original**:

1. added texture support, textures in **<0.png to 3.png> bind to iTexture<0-3>**
2. added FrameBuffers, same to Buffer<A-D> on Shadertoy, **file name Buf<0-3>.glsl**, bind to *iChannel<0-3>* and *u_channel<0-3>*
3. added encoding to \*.mov (frames without compression), \*.webm (v8 codec), both format **support RGBA** (video with alpha), added *--bitrate* option to set video bitrate(format 1M 2M..etc)
4. fixed iTime(start from 0 on shader launch), iFrame work, iTimeDelta, and other

**Warning, when result video does not look the same as on Shadertoy:**

Many shaders(even top rated) on Shadertoy may use lots of unitialized variables and clamp(1,0,-1)/pow(-1,-1)/(0/0)/...etc, that work in not same way(have not same result) in OpenGL and webbrowser Angle/GLES, black screen(or other random "results") because of this. 

Also **remember to set Alpha in main_image.glsl** when recording rgba video.

And check for used **buffers and textures parameters**, this script has *clamp_to_edge* with *linear* interpolation for buffers, and *repeat* with *linear* without *y-flip* for textures, Mipmaps not supported.

Example
-----------------

each shader(buffer) use static bindings iChannel0->Buf0.glsl, iChannel1->Buf1.glsl, iChannel2->Buf2.glsl, iChannel3->Buf3.glsl, also **added renamed copy of each channel** *sampler2D u_channel<0-3>*, to rebind inside of .glsl shader(using define)

if you need "change" channel order for shader, use in .glsl file (example set BufA as BufC, and BufC as Texture0(0.png file))

.. code-block:: C

	#define iChannel0 u_channel3
	#define iChannel3 iTexture0
	
	
use same way to bind iTexture<0-3> as iChannel<0-3> *#define iChannel0 iTexture0*

**check examples folders**, command to encode example:

.. code-block:: bash

	 cd example_shadertoy_fbo
	 python3 ../shadertoy-render.py --output 1.mp4 --size=800x450 --rate=30 --duration=5.0 --bitrate=5M main_image.glsl

to record \*.mov or \*.webm just change output file to *.webm* or *.mov*

**Example_shadertoy_fbo** `shadertoy link src <https://www.shadertoy.com/view/WlcBWr>`_ webm video recorded with RGBA and test for correct buffers queue `video link <https://danilw.github.io/GLSL-howto/shadertoy-render/video_with_alpha_result.webm>`_


Windows OS instruction to launch: (tested summer 2022 works)
-----------------

1. **install** `python3 <https://www.python.org/downloads/>`_ python 3.10 or latest, **click Add Python to PATH** in setup Window
2. press *Win+R* write **cmd** to launch console
3. in Windows console write

.. code-block:: bash
	
	pip install vispy
	
	pip install watchdog
	
	pip install glfw
	
	pip install Pillow

4. **download** `ffmpeg-git-full <https://ffmpeg.org/download.html#build-windows>`_ (example - Windows builds from gyan - ffmpeg-git-full.7z) and extract
5. **download** or clone this **shadertoy-to-video-with-FBO**
6. open **shadertoy-render.py in text editor**
7. edit line 41 to location of *ffmpeg.exe* downloaded and extracted on step 5 **notice that / used as separator**
8. press *Win+R* write **cmd** to launch console and launch command, first command path is location of example folder

	> cd C:\\shadertoy-to-video-with-FBO-master\\example_shadertoy_fbo
	
	> python ../shadertoy-render.py --output 1.mp4 --size=800x450 --rate=30 --duration=5.0 --bitrate=5M main_image.glsl


Useful ffmpeg commands:
-----------------

To **exptract .png frames with Alpha without compression**:

Two options:

1. if you need **just a single frame** - add *--interactive* to this script command line, and press S(keyboard) to save frame.
2. **for many frames** - save video as .mov (change file format in comand line) and then:

.. code-block:: bash

        ffmpeg -i video.mov -vf fps=1 "frames/out%d.png"


To convert **Video to Gif** ffmpeg commands:

best quality (Linux only) delay = 100/fps

.. code-block:: bash

        ffmpeg -i video.mp4 -vf "fps=25,scale=480:-1:flags=lanczos" -c:v pam -f image2pipe - | convert -delay 4 - -loop 0 -layers optimize output.gif

not best quality (work on Windows and Linux)

.. code-block:: bash

        ffmpeg -i video.mp4 -vf "fps=25,scale=640:-1:flags=lanczos" output.gif

