from aws_setup import *
from pathlib import *

parser = argparse.ArgumentParser(description='Fast.ai ImageNet Training')

parser.add_argument('-p', '--project-name', required=True, type=str,
                    help='Name this experiment/project. It is also the instance name')
parser.add_argument('-i', '--instance-type', required=True, type=str,
                    help='Instance type')
parser.add_argument('-vpc', '--vpc-name', default='fast-ai', type=str,
                    help='AWS VPC to create instance on (default: fast-ai)')
parser.add_argument('-vs', '--volume-size', default=500, type=int,
                    help='Size of ebs volume to create')
parser.add_argument('-del', '--delete-ebs', action='store_true',
                    help='Delete ebs volume instance termination (default: True)')
parser.add_argument('-efs', '--efs-name', type=str,
                    help='Name of efs volume to attach (default: fast-ai-efs)')
parser.add_argument('-ebs', '--ebs-name', type=str,
                    help='Name of ebs volume to attach.')
parser.add_argument('-r', '--run-script', type=str,
                    help='Run custom script')
parser.add_argument('-fast', '--use-fastai', action='store_true',
                    help='Train imagenet with fastai library.')
parser.add_argument('-nv', '--use-nvidia', action='store_true',
                    help='Train imagenet with nvidia library.')
parser.add_argument('-sargs', '--script-args', type=str, default='',
                    help='Arguments to pass in when running script. Ex: "-a resnet50 -j 7 --epochs 100 -b 128 --loss-scale 128 --fp16"')
parser.add_argument('-t', '--terminate', action='store_true',
                    help='Terminate instance after script is run.')
parser.add_argument('-ami', type=str,
                    help='AMI type')
parser.add_argument('-price', type=str,
                    help='Spot price')

args = parser.parse_args()

def launch_instance(instance_name, launch_specs, itype):
    instance = None
    if itype == 'demand':
        print('Starting on demand instance')
        instance = create_instance(instance_name, launch_specs)
    elif itype == 'spot':
        spot_prices = get_spot_prices()
        print('Creating Spot. Prices:', {k:v for (k,v) in spot_prices.items() if args.instance_type[:2] in k})
        instance = create_spot_instance(instance_name, launch_specs, spot_price=args.price)
    elif itype == 'cancel':
        print('Cancelling request...')
        return
    if not instance:
        itype = input("Instance creation error. Try again? (spot/demand/cancel)\n")
        return launch_instance(instance_name, launch_specs, itype)
    return instance

def attach_volumes(instance, client):
    if (not args.ebs_name) and (not args.efs_name): return
    if args.efs_name:
        attach_efs(args.efs_name, client)
    if args.ebs_name:
        attach_volume(instance, args.ebs_name, device='/dev/xvdf')
        mount_volume(client, device='/dev/xvdf', mount_dir='ebs_mount')


def run_script(client):
    if args.use_fastai:
        if args.run_script: print('Cannot run both run script and fastai at the same time. Ignoring run script')
        if not args.script_args: print('Must pass in script arguments to run fastai'); return 
        args.run_script = Path.cwd()/'upload_scripts/train_imagenet.sh'
        args.script_args += f' -p {args.project_name}'
    elif args.use_nvidia:
        if args.run_script: print('Cannot run both run script and fastai at the same time. Ignoring run script')
        if not args.script_args: print('Must pass in script arguments to run fastai'); return
        args.run_script = Path.cwd()/'upload_scripts/train_nv.sh'
        args.script_args += f' -p {args.project_name}'

    tsess = TmuxSession(client, 'imagenet')
    script_loc = Path(args.run_script)
    script_loc = Path(script_loc.expanduser())
    upload_file(client, script_loc, script_loc.name)
    run_cmd = f'bash {script_loc.name} {args.script_args}'
    tsess.run_command(run_cmd)
    print('Running command:', run_cmd)
    tmux_cmd = tsess.get_tmux_command()
    print(f'Tmux: {tmux_cmd}')
    

def main():
    instance_name = f'{args.vpc_name}-{args.project_name}'
    instance = get_instance(instance_name)
    if instance: 
        print(f'Instance with name already found with name: {instance_name}. Connecting to this instead')
        instance.start()
    else:
        vpc = get_vpc(args.vpc_name);
        launch_specs = LaunchSpecs(vpc, instance_type=args.instance_type, volume_size=args.volume_size, delete_ebs=args.delete_ebs, ami=args.ami)
        launch_specs.volume_type = 'io1'
        instance = launch_instance(instance_name, launch_specs.build(), 'spot')
        
    if not instance: print('Instance failed.'); return;

    client = connect_to_instance(instance)
    print(f'Completed.\nSSH: ', get_ssh_command(instance))

    try:
        attach_volumes(instance, client)
    except Exception as e:
        print('Could not attach storage:', e)


    run_script(client)

main()


