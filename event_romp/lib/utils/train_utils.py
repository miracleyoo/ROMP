import sys,os
import random
import torch
import numpy as np
import logging
from unfreeze_layers import unfreeze_head_dict

def justify_detection_state(detection_flag, reorganize_idx):
    if detection_flag.sum() == 0:
        detection_flag = False
    else:
        reorganize_idx = reorganize_idx[detection_flag.bool()].long()
        detection_flag = True
    return detection_flag, reorganize_idx

def copy_state_dict(cur_state_dict, pre_state_dict, drop_prefix='', fix_loaded=False, backbone='resnet', partial_freeze=False):
    success_layers, failed_layers = [], []
    # print("Current state dict keys: ", cur_state_dict.keys())
    # print("Pretrained state dict keys: ", pre_state_dict.keys())
    def _get_params(key):
        key = key.replace(drop_prefix,'')
        # key = prefix + key
        
        if key in pre_state_dict or ('module.'+key) in pre_state_dict:
            return pre_state_dict[key]
        return None

    unfreeze_heads = unfreeze_head_dict[backbone]
    
    for k in cur_state_dict.keys():
        v = _get_params(k)
        if partial_freeze and any([k.startswith(uh) for uh in unfreeze_heads]):
            continue

        try:
            if v is None:
                failed_layers.append(k)
                continue
            cur_state_dict[k].copy_(v)
            if 'module.' in k:
                k=k.lstrip('module.')
            success_layers.append(k)
        except:
            logging.warning('copy param {} failed, mismatched'.format(k)) # logging.info
            continue
    if len(failed_layers)>0:
        logging.info('missing parameters of layers:{}'.format(failed_layers))
    else:
        logging.info('all parameters are loaded successfully')

    if fix_loaded and len(failed_layers)>0:
        logging.info('fixing the layers that were loaded successfully, while train the layers that failed,')
        for k in cur_state_dict.keys():
            try:
                if k in success_layers:
                    cur_state_dict[k].requires_grad=False
            except:
                logging.info('fixing the layer {} failed'.format(k))

    return success_layers

def load_model(path, model, drop_prefix='', backbone='resnet', partial_freeze=False, **kwargs):
    logging.info('using fine_tune model: {}'.format(path))
    if os.path.exists(path):
        pretrained_model = torch.load(path)
        current_model = model.state_dict()
        if isinstance(pretrained_model, dict):
            if 'model_state_dict' in pretrained_model:
                pretrained_model = pretrained_model['model_state_dict']
        copy_state_dict(current_model, pretrained_model, drop_prefix=drop_prefix, backbone=backbone, partial_freeze=partial_freeze, **kwargs)
        logging.info('loading model {} success!'.format(path))
        
    else:
        logging.warning('model {} not exist!'.format(path))
    return model

def save_single_model(model,path):
    logging.info('saving {}'.format(path))
    #model_save = {'model_state_dict':model.state_dict(),'optimizer_state_dict':optimizer.state_dict()}
    if isinstance(model, torch.nn.DataParallel):
        torch.save(model.module.state_dict(), path)
    else:
        torch.save(model.state_dict(), path)
    # torch.save(model.module.state_dict(), path)

def save_model(model, title, parent_folder=None):
    if not os.path.exists(parent_folder):
        os.makedirs(parent_folder)

    if parent_folder is not None:
        title = os.path.join(parent_folder, title)
    # better results if not load previous optimizer, start a new optimizer.
    save_single_model(model, title)

def process_idx(reorganize_idx, vids=None):
    result_size = reorganize_idx.shape[0]
    reorganize_idx = reorganize_idx.cpu().numpy()
    used_idx = reorganize_idx[vids] if vids is not None else reorganize_idx
    used_org_inds = np.unique(used_idx)
    per_img_inds = [np.where(reorganize_idx==org_idx)[0] for org_idx in used_org_inds]

    return used_org_inds, per_img_inds


def determine_rendering_order(rendered_img, thresh=0.):
    main_renders = rendered_img[0]
    main_render_mask = (main_renders[:, :, -1] > thresh).cpu().numpy()
    H, W = main_renders.shape[:2]
    render_scale_map = np.zeros((H, W)) + 1
    render_scale_map[main_render_mask] = main_render_mask.sum().item()
    for jdx in range(1,len(rendered_img)):
        other_renders = rendered_img[jdx]
        other_render_mask = (other_renders[:, :, -1] > thresh).cpu().numpy()
        render_scale_map_other = np.zeros((H, W))
        render_scale_map_other[other_render_mask] = other_render_mask.sum().item()
        other_render_mask = render_scale_map_other>render_scale_map
        render_scale_map[other_render_mask] = other_render_mask.sum().item()
        main_renders[other_render_mask] = other_renders[other_render_mask]
    return main_renders[None]



# def process_idx(reorganize_idx, vids=None):
#     result_size = reorganize_idx.shape[0]
#     reorganize_idx = reorganize_idx.cpu().numpy()
#     used_idx = reorganize_idx[vids] if vids is not None else reorganize_idx
#     used_idx_org = np.unique(used_idx)
#     used_idx_now, img_idx, img_inds, count = [], [], [], 0
#     for idx, org_idx in enumerate(used_idx_org):
#         each_img_idx = np.where(reorganize_idx==org_idx)[0]
#         img_idx.append(each_img_idx)
#         used_idx_now.append(each_img_idx[0])
#         img_inds.append(np.arange(len(each_img_idx))+count) 
#         count+=len(each_img_idx)
#     if len(img_idx)!=0:
#         all_idx = np.concatenate(img_idx)
#     used_idx_now = np.array(used_idx_now)
#     return used_idx_org, used_idx_now, all_idx, img_inds

def fix_backbone(params, exclude_key=['backbone.']):
    for exclude_name in exclude_key:
        for index,(name,param) in enumerate(params.named_parameters()):
            if exclude_name in name:
                param.requires_grad =False
    logging.info('Fix params that include in {}'.format(exclude_key))
    return params


def print_dict(dt):
    print('Dict has {} keys: {}'.format(len(list(dt.keys())), list(dt.keys())))
    for key, value in dt.items():
        if isinstance(value, dict):
            print('Dict {}'.format(key))
            print_dict(value)
        elif isinstance(value, list):
            print('List {}, length {}'.format(key, len(value)))
        elif isinstance(value, tuple):
            print('Tuple {}, length {}'.format(key, len(value)))
        elif isinstance(value, np.ndarray):
            print('Np {}, shape {}, dtype {}'.format(key, value.shape, value.dtype))
        elif torch.is_tensor(value):
            print('Torch Tensor {}, shape {}, on {}'.format(key, value.shape, value.device))
        else:
            print(key, value)
    print('-'*20)

def get_remove_keys(dt, keys=[]):
    targets = []
    for key in keys:
        targets.append(dt[key])
    for key in keys:
        del dt[key]
    return targets


def reorganize_items(items, reorganize_idx):
    items_new = [[] for _ in range(len(items))]
    for idx, item in enumerate(items):
        for ridx in reorganize_idx:
            items_new[idx].append(item[ridx])
    return items_new


def exclude_params(params, excluding=['parser', 'loss']):
    del_keys = []
    for exclude_name in excluding:
        for index,(name,param) in enumerate(params.named_parameters()):
            if exclude_name in name:
                del_keys.append(name)
            param.requires_grad =False
    logging.info('Remove {} params from optimzer list'.format(del_keys))
    return params


def print_net(model,name):
    print(name,'requires_grad')
    states = []
    for param in model.parameters():
        if not param.requires_grad:
            states.append(param.name)
    if len(states)<1:
        print('All parameters are trainable.')
    else:
        print(states)

def write2log(log_file, massage):
    with open(log_file, "a") as f:
        f.write(massage)

def process_pretrained(model_dict):
    keys = list(model_dict.keys())
    for key in keys:
        if 'module.net.features' in key:
            num = int(key.split('.')[-2])
            if num==0:
                continue
            type_name = key.split('.')[-1]
            model_dict['module.net.features.'+str(num+1)+'.'+type_name] = model_dict[key]
    return model_dict
    

def train_entire_model(model, backbone='resnet', partial_freeze=False):
    exclude_layer = []
    
    unfreeze_heads = unfreeze_head_dict[backbone]
    for name, param in model.named_parameters():
        if partial_freeze:
            unfreeze_flag = any([name.startswith(uh) for uh in unfreeze_heads])
        else:
            unfreeze_flag = True
            
        if 'smpl' in name and param.requires_grad:
            unfreeze_flag = False
        if not unfreeze_flag:
            param.requires_grad = False
            exclude_layer.append(name)
            logging.info('freeze layer {}'.format(name))
        # else:
        #     param.requires_grad = True
                
    # for name, param in model.named_parameters():
    #     if 'smpl' not in name:
    #         param.requires_grad = True
    #     else:
    #         if param.requires_grad:
    #             exclude_layer.append(name)
    #         param.requires_grad =False
    if len(exclude_layer)==0:
        logging.info('Training all layers.')
    else:
        logging.info('Train all layers, except: {}'.format(exclude_layer))

    return model

def init_seeds(seed=0, cuda_deterministic=False):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    # Speed-reproducibility tradeoff https://pytorch.org/docs/stable/notes/randomness.html
    if cuda_deterministic:  # slower, more reproducible
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    else:  # faster, less reproducible
        torch.backends.cudnn.deterministic = False
        torch.backends.cudnn.benchmark = True
        torch.backends.cudnn.enabled = True