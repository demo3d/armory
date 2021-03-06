import bpy
import os
import sys
import subprocess
import json
import re
import armutils
import assets

def add_irr_assets(output_file_irr):
    assets.add(output_file_irr + '.arm')

def add_rad_assets(output_file_rad, rad_format, num_mips):
    assets.add(output_file_rad + '.' + rad_format)
    for i in range(0, num_mips):
        assets.add(output_file_rad + '_' + str(i) + '.' + rad_format)

# Generate probes from environment map
def write_probes(image_filepath, disable_hdr, cached_num_mips, generate_radiance=True):
    envpath = 'build/compiled/Assets/envmaps'
    
    if not os.path.exists(envpath):
        os.makedirs(envpath)

    base_name = armutils.extract_filename(armutils.safe_assetpath(image_filepath)).rsplit('.', 1)[0]
    
    # Assets to be generated
    output_file_irr = envpath + '/' + base_name + '_irradiance'
    if generate_radiance:
        output_file_rad = envpath + '/' + base_name + '_radiance'
        rad_format = 'jpg' if disable_hdr else 'hdr'

    # Radiance & irradiance exists, keep cache
    basep = envpath + '/' + base_name
    if os.path.exists(basep + '_irradiance.arm'):
        if not generate_radiance or os.path.exists(basep + '_radiance_0.' + rad_format):
            add_irr_assets(output_file_irr)
            if generate_radiance:
                add_rad_assets(output_file_rad, rad_format, cached_num_mips)
            return cached_num_mips
    
    # Get paths
    sdk_path = armutils.get_sdk_path()

    if armutils.get_os() == 'win':
        cmft_path = sdk_path + '/armory/tools/cmft/cmft.exe'
        kraffiti_path = sdk_path + '/win32/Kha/Kore/Tools/kraffiti/kraffiti.exe'
    elif armutils.get_os() == 'mac':
        cmft_path = sdk_path + '/armory/tools/cmft/cmft-osx'
        kraffiti_path = sdk_path + '/"Kode Studio.app"/Contents/Kha/Kore/Tools/kraffiti/kraffiti-osx'
    else:
        cmft_path = sdk_path + '/armory/tools/cmft/cmft-linux64'
        kraffiti_path = sdk_path + '/linux64/Kha/Kore/Tools/kraffiti/kraffiti-linux64'
    
    output_gama_numerator = '1.0' if disable_hdr else '2.2'
    input_file = armutils.safe_assetpath(image_filepath)
    
    # Scale map
    wrd = bpy.data.worlds['Arm']
    target_w = int(wrd.generate_radiance_size)
    target_h = int(target_w / 2)
    scaled_file = output_file_rad + '.' + rad_format

    if armutils.get_os() == 'win':
        output = subprocess.check_output([ \
            kraffiti_path,
            'from=' + input_file.replace(' ', '\ '),
            'to=' + scaled_file.replace(' ', '\ '),
            'format=' + rad_format,
            'width=' + str(target_w),
            'height=' + str(target_h)])
    else:
        output = subprocess.check_output([ \
            kraffiti_path + \
            ' from="' + input_file + '"' + \
            ' to="' + scaled_file + '"' + \
            ' format=' + rad_format + \
            ' width=' + str(target_w) + \
            ' height=' + str(target_h)], shell=True)

    # Generate irradiance
    # gama_options = ''
    # if disable_hdr:
        # gama_options = \
        # ' --inputGammaNumerator 2.2' + \
        # ' --inputGammaDenominator 1.0' + \
        # ' --outputGammaNumerator 1.0' + \
        # ' --outputGammaDenominator ' + output_gama_numerator
    
    # Irradiance spherical harmonics
    if armutils.get_os() == 'win':
        subprocess.call([ \
            cmft_path,
            '--input', scaled_file.replace(' ', '\ '),
            '--filter', 'shcoeffs',
            #gama_options + \
            '--outputNum', '1',
            '--output0', output_file_irr])
    else:
        subprocess.call([ \
            cmft_path + \
            ' --input ' + '"' + scaled_file + '"' + \
            ' --filter shcoeffs' + \
            #gama_options + \
            ' --outputNum 1' + \
            ' --output0 ' + output_file_irr], shell=True)

    sh_to_json(output_file_irr)
    add_irr_assets(output_file_irr)
    
    # Mip-mapped radiance
    if generate_radiance == False:
        return cached_num_mips

    # 4096 = 256 face
    # 2048 = 128 face
    # 1024 = 64 face
    face_size = target_w / 8
    if target_w == 2048:
        mip_count = 9
    elif target_w == 1024:
        mip_count = 8
    else:
        mip_count = 7
    
    use_opencl = 'true' if wrd.arm_gpu_processing else 'false'

    if armutils.get_os() == 'win':
        subprocess.call([ \
            cmft_path,
            '--input', input_file.replace(' ', '\ '),
            '--filter', 'radiance',
            '--dstFaceSize', str(face_size),
            '--srcFaceSize', str(face_size),
            '--excludeBase', 'false',
            # '--mipCount', str(mip_count),
            '--glossScale', '7',
            '--glossBias', '3',
            '--lightingModel', 'blinnbrdf',
            '--edgeFixup', 'none',
            '--numCpuProcessingThreads', '4',
            '--useOpenCL', use_opencl,
            '--clVendor', 'anyGpuVendor',
            '--deviceType', 'gpu',
            '--deviceIndex', '0',
            '--generateMipChain', 'true',
            '--inputGammaNumerator', '2.2',
            '--inputGammaDenominator', '1.0',
            '--outputGammaNumerator', '1.0',
            '--outputGammaDenominator', output_gama_numerator,
            '--outputNum', '1',
            '--output0', output_file_rad.replace(' ', '\ '),
            '--output0params', 'hdr,rgbe,latlong'])
    else:
        subprocess.call([ \
            cmft_path + \
            ' --input "' + input_file + '"' + \
            ' --filter radiance' + \
            ' --dstFaceSize ' + str(face_size) + \
            ' --srcFaceSize ' + str(face_size) + \
            ' --excludeBase false' + \
            #' --mipCount ' + str(mip_count) + \
            ' --glossScale 7' + \
            ' --glossBias 3' + \
            ' --lightingModel blinnbrdf' + \
            ' --edgeFixup none' + \
            ' --numCpuProcessingThreads 4' + \
            ' --useOpenCL ' + use_opencl + \
            ' --clVendor anyGpuVendor' + \
            ' --deviceType gpu' + \
            ' --deviceIndex 0' + \
            ' --generateMipChain true' + \
            ' --inputGammaNumerator 2.2' + \
            ' --inputGammaDenominator 1.0' + \
            ' --outputGammaNumerator 1.0' + \
            ' --outputGammaDenominator ' + output_gama_numerator + \
            ' --outputNum 1' + \
            ' --output0 "' + output_file_rad + '"' + \
            ' --output0params hdr,rgbe,latlong'], shell=True)

    # Remove size extensions in file name
    mip_w = int(face_size * 4)
    mip_base = output_file_rad + '_'
    mip_num = 0
    while mip_w >= 4:
        mip_name = mip_base + str(mip_num)
        os.rename(
            mip_name + '_' + str(mip_w) + 'x' + str(int(mip_w / 2)) + '.hdr',
            mip_name + '.hdr')
        mip_w = int(mip_w / 2)
        mip_num += 1

    # Append mips       
    generated_files = []
    for i in range(0, mip_count):
        generated_files.append(output_file_rad + '_' + str(i))
    
    # Convert to jpgs
    if disable_hdr is True:
        for f in generated_files:
            if armutils.get_os() == 'win':
                subprocess.call([ \
                    kraffiti_path,
                    'from=' + f + '.hdr',
                    'to=' + f + '.jpg',
                    'format=jpg'])
            else:
                subprocess.call([ \
                    kraffiti_path + \
                    ' from=' + f + '.hdr' + \
                    ' to=' + f + '.jpg' + \
                    ' format=jpg'], shell=True)
            os.remove(f + '.hdr')
    
    # Scale from (4x2 to 1x1>
    for i in range (0, 2):
        last = generated_files[-1]
        out = output_file_rad + '_' + str(mip_count + i)
        if armutils.get_os() == 'win':
            subprocess.call([ \
                kraffiti_path,
                'from=' + last + '.' + rad_format,
                'to=' + out + '.' + rad_format,
                'scale=0.5',
                'format=' + rad_format], shell=True)
        else:
            subprocess.call([ \
                kraffiti_path + \
                ' from=' + last + '.' + rad_format + \
                ' to=' + out + '.' + rad_format + \
                ' scale=0.5' + \
                ' format=' + rad_format], shell=True)
        generated_files.append(out)
    
    mip_count += 2

    add_rad_assets(output_file_rad, rad_format, mip_count)

    return mip_count

# Parse sh coefs produced by cmft into json array
def sh_to_json(sh_file):
    with open(sh_file + '.c') as f:
        sh_lines = f.read().splitlines()
    band0_line = sh_lines[5]
    band1_line = sh_lines[6]
    band2_line = sh_lines[7]

    irradiance_floats = []
    parse_band_floats(irradiance_floats, band0_line)
    parse_band_floats(irradiance_floats, band1_line)
    parse_band_floats(irradiance_floats, band2_line)
    
    sh_json = {}
    sh_json['irradiance'] = irradiance_floats
    armutils.write_arm(sh_file + '.arm', sh_json)
    
    # Clean up .c
    os.remove(sh_file + '.c')

def parse_band_floats(irradiance_floats, band_line):
    string_floats = re.findall(r'[-+]?\d*\.\d+|\d+', band_line)
    string_floats = string_floats[1:] # Remove 'Band 0/1/2' number
    for s in string_floats:
        irradiance_floats.append(float(s))

def write_sky_irradiance(base_name):
    wrd = bpy.data.worlds['Arm']

    if wrd.generate_radiance_sky_type == 'Hosek':
        # Hosek spherical harmonics
        irradiance_floats = [1.5519331988822218,2.3352207154503266,2.997277451988076,0.2673894962434794,0.4305630474135794,0.11331825259716752,-0.04453633521758638,-0.038753175134160295,-0.021302768541875794,0.00055858020486499,0.000371654770334503,0.000126606145406403,-0.000135708721978705,-0.000787399554583089,-0.001550090690860059,0.021947399048903773,0.05453650591711572,0.08783641266630278,0.17053593578630663,0.14734127083304463,0.07775404698816404,-2.6924363189795e-05,-7.9350169701934e-05,-7.559914435231e-05,0.27035455385870993,0.23122918445556914,0.12158817295211832]
        for i in range(0, len(irradiance_floats)):
            irradiance_floats[i] /= 2;
    else: # Fake
        irradiance_floats = [0.5282714503101548,0.6576873502619733,1.0692444882409775,0.17108712865136044,-0.08840906601412168,-0.5016437779078063,-0.05123227009753221,-0.06724088656181595,-0.07651659183264257,-0.09740705087869408,-0.19569235551561795,-0.3087497307203731,0.056717192983076405,0.1109186355691673,0.20616582000220154,0.013898321643280141,0.05985657405787638,0.12638202463080392,-0.003224443014484806,0.013764449325286695,0.04288850064700093,0.1796545401960917,0.21595731080039757,0.29144356515614844,0.10152875101705996,0.2651761450155488,0.4778582813756466]

    envpath = 'build/compiled/Assets/envmaps'
    if not os.path.exists(envpath):
        os.makedirs(envpath)
    
    output_file = envpath + '/' + base_name + '_irradiance'
    
    sh_json = {}
    sh_json['irradiance'] = irradiance_floats
    armutils.write_arm(output_file + '.arm', sh_json)

    assets.add(output_file + '.arm')

def write_color_irradiance(base_name, col):
    # Constant color
    irradiance_floats = [col[0], col[1], col[2]]
    for i in range(0, 24):
        irradiance_floats.append(0.0)
    
    envpath = 'build/compiled/Assets/envmaps'
    if not os.path.exists(envpath):
        os.makedirs(envpath)
    
    output_file = envpath + '/' + base_name + '_irradiance'
    
    sh_json = {}
    sh_json['irradiance'] = irradiance_floats
    armutils.write_arm(output_file + '.arm', sh_json)

    assets.add(output_file + '.arm')
