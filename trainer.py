import sys
import logging
import copy
import torch
import torch.nn as nn
import torchvision
import torchvision.models as models
from utils import factory
from utils.data_manager import DataManager
from utils.toolkit import count_parameters
from collections import OrderedDict
import os
import wandb 
import pickle




def train(args):
    seed_list = copy.deepcopy(args["seed"])
    device = copy.deepcopy(args["device"])

    for seed in seed_list:
        args["seed"] = seed
        args["device"] = device
        _train(args)


def _train(args):

    init_cls = 0 if args ["init_cls"] == args["increment"] else args["init_cls"]
    logs_name = "logs/{}/{}/{}/{}".format(args["model_name"],args["dataset"], init_cls, args['increment'])
    
    run = wandb.init(
        project=args["wb-project"],
        name=''.join([
            args["dataset"], "_",
            args["model_name"], "_seed_",
            str(args["seed"])
        ]), 
        config={
            "model_name": args["model_name"],
            "conv_type": args["convnet_type"],
            "dataset": args["dataset"],
            "prefix": args["prefix"]
        }
    )


    
    if not os.path.exists(logs_name):
        os.makedirs(logs_name)

    logfilename = "logs/{}/{}/{}/{}/{}_{}_{}".format(
        args["model_name"],
        args["dataset"],
        init_cls,
        args["increment"],
        args["prefix"],
        args["seed"],
        args["convnet_type"],
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(filename)s] => %(message)s",
        handlers=[
            logging.FileHandler(filename=logfilename + ".log"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    _set_random()
    _set_device(args)
    print_args(args)
    data_manager = DataManager(
        args["dataset"],
        args["shuffle"],
        args["seed"],
        args["init_cls"],
        args["increment"],
    )
    model = factory.get_model(args["model_name"], args)

    cnn_curve, nme_curve = {"top1": [], "top5": []}, {"top1": [], "top5": []}
    for task in range(data_manager.nb_tasks):
        logging.info("All params: {}".format(count_parameters(model._network)))
        logging.info(
            "Trainable params: {}".format(count_parameters(model._network, True))
        )
        model.incremental_train(data_manager)
        cnn_accy, nme_accy = model.eval_task()
        model.after_task()
        
        new_state_dict = OrderedDict()
        for key, value in model._network.state_dict().items():
          if 'convnet.' in key:
            new_key = key.replace('convnet.','')
            if 'conv1.0' in new_key:
              new_key = new_key.replace('conv1.0','conv1')
            if 'conv1.1' in new_key:
              new_key = new_key.replace('conv1.1','bn1')
            new_state_dict[new_key] = value
          else:
            new_state_dict[key] = value
        model50 = models.resnet50()
        num_features = model._network.fc.in_features
        model50.fc = nn.Linear(num_features, 10)
        model50.load_state_dict(new_state_dict)
        
        if nme_accy is not None:
            logging.info("CNN: {}".format(cnn_accy["grouped"]))
            logging.info("NME: {}".format(nme_accy["grouped"]))

            cnn_curve["top1"].append(cnn_accy["top1"])
            cnn_curve["top5"].append(cnn_accy["top5"])

            nme_curve["top1"].append(nme_accy["top1"])
            nme_curve["top5"].append(nme_accy["top5"])

            logging.info("CNN top1 curve: {}".format(cnn_curve["top1"]))
            logging.info("CNN top5 curve: {}".format(cnn_curve["top5"]))
            logging.info("NME top1 curve: {}".format(nme_curve["top1"]))
            logging.info("NME top5 curve: {}\n".format(nme_curve["top5"]))
            
            run.log({
                "cnn_top1": cnn_accy["top1"],
                "cnn_top5": cnn_accy["top5"],
                "nme_top1": nme_accy["top1"],
                "nme_top5": nme_accy["top5"]
            })
        else:
            logging.info("No NME accuracy.")
            logging.info("CNN: {}".format(cnn_accy["grouped"]))

            cnn_curve["top1"].append(cnn_accy["top1"])
            cnn_curve["top5"].append(cnn_accy["top5"])

            logging.info("CNN top1 curve: {}".format(cnn_curve["top1"]))
            logging.info("CNN top5 curve: {}\n".format(cnn_curve["top5"]))
            
            run.log({
                "cnn_top1": cnn_accy["top1"],
                "cnn_top5": cnn_accy["top5"],
            })


def _set_device(args):
    device_type = args["device"]
    gpus = []

    for device in device_type:
        if device == -1:
            device = torch.device("mps")
        else:
            device = torch.device("cuda:{}".format(device))

        gpus.append(device)
        
    args["device"] = gpus


def _set_random():
    torch.manual_seed(1)
    torch.cuda.manual_seed(1)
    torch.cuda.manual_seed_all(1)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def print_args(args):
    for key, value in args.items():
        logging.info("{}: {}".format(key, value))
