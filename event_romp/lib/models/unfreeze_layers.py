resnet50_unfreeze_head=[
    'backbone.conv1',
    'backbone.bn1',
    'backbone.layer1',
    'backbone.layer2',
]

hrnet32_unfreeze_head=[
    'backbone.conv1',
    'backbone.bn1',
    'backbone.conv2',
    'backbone.bn2',
    'backbone.layer1',
]

unfreeze_head_dict = {
    'resnet': resnet50_unfreeze_head,
    'hrnet': hrnet32_unfreeze_head,
}

