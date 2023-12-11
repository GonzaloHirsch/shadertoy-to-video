# Shadertoy to Video

This is originally forked from https://github.com/danilw/shadertoy-to-video-with-FBO and adapted to run in MacOS with Shadertoy shaders.

Disclaimer: The focus of this repository is to ensure that this library is compatible with MacOS since that is the use case I'm going for.

The main change to get this working in MacOS with up-to-date Shadertoy GLSL shaders was to remove the pragma with an invalid version.

---

**What is it**: creating video from shaders on Shadertoy. This my fork has many changes and fixes from original.

**Windows OS** support instruction, **how to launch it on Windows OS** scroll down. (tested/works on Linux and Windows)

Original `Youtube playlist <https://youtube.com/playlist?list=PLzDEnfuEGFHv9AF11F0UYXXx9sdfXqu8M>`_ - videos created from my shaders using this script. `GLSL Auto Tetris video <https://youtu.be/rcgpwVLydLw>`_ also recorded by this script.

**Uploading created video to Twitter/Instagram** - pixel format set to _yuv420p_ for _libx264_ codec and _.mp4_ video can be uploaded to any social platform without problems.

## Note 2023, about vispy and "too many backends":

If you have error on using glfw backend that I set as default - change it in `864 line in shadertoy-render.py <https://github.com/GonzaloHirsch/shadertoy-to-video/blob/master/shadertoy-render.py#L864>`\_

For example: _vispy.use('egl')_

I had some errors with glfw on AMD GPU, and I just keep as it is using glfw by default because last year I had error with egl backend on Nvidia and egl not working anymore `in Colab <https://github.com/vispy/vispy/issues/2469#issuecomment-1513538902>`\_ - _Vispy and OpenGL is complete mess_, you can contact me on discord link above. _For me now in 2023 - glfw working on Nvidia, and egl on AMD._

**Supported** - Buffers A-D same as on Shadertoy. Images. `discard` supported in buffers and image shader.

**Supported** recording video format: (look line `929 in shadertoy-render.py <https://github.com/danilw/shadertoy-to-video-with-FBO/blob/master/shadertoy-render.py#L929>`\_ for encoding parameters)

- `*.mp4` - h264, alpha ignored
- `*.webm` - v8 codec, support alpha
- `*.mov` - frames without compression, support alpha

**Supported** - video input (instead of texture), look **example_video_input** description below.

_Not supported_ - Cubemaps, Shader-Cubemap, 3d texture, audio input not supported. (2d textures without mipmaps)

## Shader uniforms:

`iChannel0 to iChannel3` uniform is **Buf0.glsl to Buf3.glsl file**.

`iTexture0 to iTexture3` uniform is **0.png to 3.png file**

if you want/need **to change order of iChannels** - added renamed copy `u_channel0` to `u_channel3` uniform

```c
#define iChannel0 u_channel3
#define iChannel3 iTexture0
```

## Examples:

**example_one_shader** - New shader on Shadertoy, single shader example.

**example_shadertoy_fbo** - test for Buffer queue order to be same as on Shadertoy, `Shadertoy link src <https://www.shadertoy.com/view/WlcBWr>`_ webm video recorded with RGBA and test for correct buffers queue `video link <https://danilw.github.io/GLSL-howto/shadertoy-render/video_with_alpha_result.webm>`_

**example_textures** - example using textures. _Shadertoy textures_ can be found on `Shadertoy Unofficial <https://shadertoyunofficial.wordpress.com/2019/07/23/shadertoy-media-files/>`\_

Command to encode example:

```bash
cd example_shadertoy_fbo
python3 ../shadertoy-render.py --output 1.mp4 --size=800x450 --rate=30 --duration=5.0 --bitrate=5M main_image.glsl
```

**example_video_input** - example for video input. You need to convert/extract video to "png frames". **Look _render.sh_ file in _example_video_input_ for recording and converting comands**. _Output result of this example expected to be "V-flipped"_, v-flip your texture in shader if needed.

## Command line options:

`--output 1.mp4` - file name for video file.

`--size=800x450` - resolution of video for recording, for 1080p set `1920x1080`

`--rate=30` - frame rate, FPS for shader

`--duration=5.0` - duration in seconds, support fractional part of second example `2.5` two sec and 500ms (half of second)

`--bitrate=5M` - bitrate of video, used only for `mp4` and `webm` file format

`--tile-size=512` **tile rendering** - useful when you want render very slow shader for 4k video, or you have very slow GPU. Also useful for Windows OS to avoid driver crash when frames rendered for longer than 2 sec.

**Tile rendering works only on Image shader** (`main_image.glsl` file). Buffers (A-D) still rendered full frame at once. (_also remember_ that `discard` in shader will be broken when used tile rendering).

## When recording visual result not equal to Shadertoy:

Many shaders(even top rated) on Shadertoy may use lots of unitialized variables and clamp(1,0,-1)/pow(-1,2)/(0/0)/normalize(0)...etc, that work in not same way(have not same result) in OpenGL and webbrowser Angle/GLES, black screen(or other random "results") because of this. (also sin-noise could be broken in OpenGL)

**The only way to fix your shader** - is hand debugging and fixing all bugs.

Also **remember to set Alpha in main_image.glsl** when recording rgba video.

And check for used **buffers and textures parameters**, this script has _clamp_to_edge_ with _linear_ interpolation for buffers, and _repeat_ with _linear_ without _y-flip_ for textures, Mipmaps not supported.

## Windows OS instruction to launch: (tested summer 2022 works)

1. **install** `python3 <https://www.python.org/downloads/>`\_ python 3.10 or latest, **click Add Python to PATH** in setup Window
2. press _Win+R_ write **cmd** to launch console
3. in Windows console write

```bash
pip install vispy watchdog glfw Pillow imageio PyQt5
```

4. **download** `ffmpeg-git-full <https://ffmpeg.org/download.html#build-windows>`\_ (example - Windows builds from gyan - ffmpeg-git-full.7z) and extract
5. **download** or clone this **shadertoy-to-video-with-FBO**
6. open **shadertoy-render.py in text editor**
7. edit line 41 to location of _ffmpeg.exe_ downloaded and extracted on step 4 **notice that / used as separator**
8. press _Win+R_ write **cmd** to launch console and launch command, first command path is location of example folder
   ```bash
   cd C:\\shadertoy-to-video-with-FBO-master\\example_shadertoy_fbo
   python ../shadertoy-render.py --output 1.mp4 --size=800x450 --rate=30 --duration=5.0 --bitrate=5M main_image.glsl
   ```

## Useful ffmpeg commands:

To **exptract .png frames with Alpha without compression**:

Two options:

1. if you need **just a single frame** - add _--interactive_ to this script command line, and press S(keyboard) to save frame.
2. **for many frames** - save video as .mov (change file format in comand line) and then:

```bash
ffmpeg -i video.mov -vf fps=1 "frames/out%d.png"
```

To convert **Video to Gif** ffmpeg commands:

best quality (Linux only) delay = 100/fps

```bash
ffmpeg -i video.mp4 -vf "fps=25,scale=480:-1:flags=lanczos" -c:v pam -f image2pipe - | convert -delay 4 - -loop 0 -layers optimize output.gif
```

not best quality (work on Windows and Linux)

```bash
ffmpeg -i video.mp4 -vf "fps=25,scale=640:-1:flags=lanczos" output.gif
```

## Useful ImageMagic commands:

**When recording cubemap** (from 6 sides) - remember to set _rep=False_ in functions _set_Buf_texture_input_ and _set_texture_input_ in _shadertoy-render.py_, to set texture as clamp_to_edge.

When used _import imageio_ in Python script - _imageio_ does not support indexed color, and _convert_ or _ffmpeg_ sometime can convert images to indexed format, look _"correct RGBA png color format"_ below to convert back.

image information `identify docs <https://imagemagick.org/script/identify.php>`\_

```bash
magick identify -verbose 1.png
```

Cut corners on image, with correct RGBA png color format:

```bash
convert '1.png' -colorspace sRGB -define png:format=png32 -define png:color-type=6 -gravity center -background transparent -extent 2048x2048 '1.png'
```
