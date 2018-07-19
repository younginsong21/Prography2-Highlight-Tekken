######### non-bidirectional version code #########

import torch.nn as nn
import torch

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
import numpy as np

from videoloader import get_loader

# Device configuration
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

h_video_path = '../../dataset/HV'
r_video_path = '../../dataset/RV'
weight_path = '../../weight/c3d.pickle'

##############################################################
######  source: https://github.com/DavideA/c3d-pytorch  ######
##############################################################
class C3D(nn.Module):
    """
    The C3D network as described in [1].
    """

    def __init__(self):
        super(C3D, self).__init__()

        self.conv1 = nn.Conv3d(3, 64, kernel_size=(3, 3, 3), padding=(1, 1, 1))
        self.pool1 = nn.MaxPool3d(kernel_size=(1, 2, 2), stride=(1, 2, 2))

        self.conv2 = nn.Conv3d(64, 128, kernel_size=(3, 3, 3), padding=(1, 1, 1))
        self.pool2 = nn.MaxPool3d(kernel_size=(2, 2, 2), stride=(2, 2, 2))

        self.conv3a = nn.Conv3d(128, 256, kernel_size=(3, 3, 3), padding=(1, 1, 1))
        self.conv3b = nn.Conv3d(256, 256, kernel_size=(3, 3, 3), padding=(1, 1, 1))
        self.pool3 = nn.MaxPool3d(kernel_size=(2, 2, 2), stride=(2, 2, 2))

        self.conv4a = nn.Conv3d(256, 512, kernel_size=(3, 3, 3), padding=(1, 1, 1))
        self.conv4b = nn.Conv3d(512, 512, kernel_size=(3, 3, 3), padding=(1, 1, 1))
        self.pool4 = nn.MaxPool3d(kernel_size=(2, 2, 2), stride=(2, 2, 2))

        self.conv5a = nn.Conv3d(512, 512, kernel_size=(3, 3, 3), padding=(1, 1, 1))
        self.conv5b = nn.Conv3d(512, 512, kernel_size=(3, 3, 3), padding=(1, 1, 1))
        self.pool5 = nn.MaxPool3d(kernel_size=(2, 2, 2), stride=(2, 2, 2), padding=(0, 1, 1))

        self.fc6 = nn.Linear(8192, 4096)
        self.fc7 = nn.Linear(4096, 4096)
        self.fc8 = nn.Linear(4096, 487)

        self.dropout = nn.Dropout(p=0.5)

        self.relu = nn.ReLU()
        self.softmax = nn.Softmax()

# only forwarding once
class GRU(nn.Module):
    def __init__(self, c3d):
        super(GRU, self).__init__()

        self.c3d = c3d
        self.temporal_pool = nn.MaxPool1d(4, 4, 0).cuda()
        self.gru = nn.GRUCell(243, 2).cuda()

        self.loss = nn.MSELoss() # loss for classification highlight/row

    def forward(self, input, true_label):
        # input_cp = input.clone() # copy input tensor for backwarding GRU

        if true_label == 'HV': # if input video is highlight clip
            self.target = np.ones([128])
        else: # if input video is row video
            self.target = np.zeros([128])

        self.target = torch.from_numpy(self.target).float().cuda()

        start = 0
        end = 48

        f_ht = torch.FloatTensor(128, 2).normal_().cuda() # (batch, hidden)
        # b_ht = torch.FloatTensor(128, 2).normal_().cuda() # (batch, hidden)

        f_loss_list = []
        # b_loss_list = []

        # forwarding once
        input = input.permute(0, 2, 1, 3, 4)  # [batch, channel, depth, height, width]

        forward_step = 0
        while end < input.shape[2]:
            x = input[:, :, start:end, :, :] # x.shape: 1, 3, 48, h, w
            h = self.c3d(x) # c3d forwarding => 1, 512, 3, 9, 9
            h = h.squeeze()
            h = h.view(1, 512, -1).permute(0, 2, 1)
            h = self.temporal_pool(h).permute(0, 2, 1).squeeze()

            f_ht = (self.gru(h.cuda(), f_ht))
            # print(f_ht.shape) # [128, 2]

            f_argmax = torch.argmax(f_ht, dim=1).float().cuda() # classification
            # print(f_argmax, f_argmax.shape) # [128]

            snp_loss = self.loss(f_argmax, self.target)
            # print("forwarding: ", forward_step, snp_loss)
            f_loss_list.append(snp_loss.data)

            start += 6
            end += 6
            forward_step += 1

        ##########################################################################

        # # backwarding once
        # input_cp = input_cp.cpu()
        # reversed_input = torch.from_numpy(np.flip(input_cp.numpy(), axis=1).copy()) # reverse input depth(axis=1) sequence
        # reversed_input = reversed_input.permute(0, 2, 1, 3, 4) # [batch, channel, depth(reversed), h, w]
        # reversed_input = reversed_input.cuda()
        #
        # start = 0
        # end = 48
        #
        # backward_step = 0
        # while end < reversed_input.shape[2]:
        #     x = reversed_input[:, :, start:end, :, :]  # x.shape: 1, 3, 48, h, w
        #     h = self.c3d(x)  # c3d forwarding => 1, 512, 3, 9, 9
        #     h = h.squeeze()
        #     h = h.view(1, 512, -1).permute(0, 2, 1)
        #     h = self.temporal_pool(h).permute(0, 2, 1).squeeze()
        #
        #     b_ht = (self.gru(h.cuda(), b_ht))
        #     # print(f_ht.shape) # [128, 2]
        #
        #     b_argmax = torch.argmax(b_ht, dim=1).float().cuda() # classification
        #     # print(f_argmax, f_argmax.shape) # [128]
        #
        #     snp_loss = self.loss(b_argmax, self.target)
        #     # print("backwarding:", backward_step, snp_loss)
        #     b_loss_list.append(snp_loss.data)
        #
        #     start += 6
        #     end += 6
        #     backward_step += 1

        f_loss = sum(f_loss_list) / forward_step
        # b_loss = sum(b_loss_list) / backward_step
        # print(f_loss, b_loss)

        # total_loss = (f_loss.item() + b_loss.item()) / 2

        return f_loss

# if __name__ == '__main__':
#     # load videos
#     h_loader, r_loader = get_loader(h_video_path, r_video_path)
#
#     for idx, (frames, scores) in enumerate(r_loader):
#         frames = frames.cuda()
#         scores = scores.cuda()
#         break
#
#     # define C3D layer
#     c3d = C3D()
#     c3d.load_state_dict(torch.load(weight_path))  # load pre-trained weight
#     c3d = c3d.cuda()
#
#     # remove c3d fc layers
#     fc_removed = list(c3d.children())[:-6]
#
#     _p3d_net = []
#     relu = nn.ReLU().cuda()
#
#     for layer in fc_removed:
#         for param in layer.parameters():
#             param.requires_grad = False  # no training
#         if layer.__class__.__name__ == 'MaxPool3d':
#             _p3d_net.extend([layer, relu])  # add activation function
#         else:
#             _p3d_net.append(layer)
#
#     c3d = nn.Sequential(*_p3d_net).cuda()  # new p3d net
#
#     gru = GRU(c3d)
#     out = gru(frames)
#
#     print(out) # tuple: length 128 for one video