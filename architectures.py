"""
Definitions and utilities for the FlowNet model
This file contains functions to define net architectures for FlowNet in Tensorflow
"""

import tensorflow as tf
import tensorflow.contrib.slim as slim
from tensorflow.python.platform import flags

import numpy as np

FLAGS = flags.FLAGS
import flownet


def lrelu(x, leak=0.1, name="lrelu"):
    if "_" in name:
        name = name + "_Relu"
    with tf.variable_scope(name):
        f1 = 0.5 * (1 + leak)
        f2 = 0.5 * (1 - leak)
        return f1 * x + f2 * abs(x)

def msra_initializer(kl, dl):
    """
    kl for kernel size, dl for filter number
    """
    stddev = math.sqrt(2. / (kl**2 * dl))
    return tf.truncated_normal_initializer(stddev=stddev)

def flownet_s(imgs_0, imgs_1, flows):
    """Build the flownet_s model
       Check train.prototxt for original caffe model
    """
    #TODO: test to normalize [0, 255] --> [-1, 1]
    #imgs_0 = imgs_0 / 127.5 - 1
    #imgs_1 = imgs_0 / 127.5 - 1
    #flows = flows*0.05
    net = tf.concat([imgs_0, imgs_1], -1 ,name='concat_0')
    # stack of convolutions
    convs = {"conv1": [64, [7, 7], 2],
             "conv2_1": [128, [5, 5], 2],  # _1 to concat easily later
             "conv3": [256, [5, 5], 2],
             "conv3_1": [256, [3, 3], 1],
             "conv4": [512, [3, 3], 2],
             "conv4_1": [512, [3, 3], 1],
             "conv5": [512, [3, 3], 2],
             "conv5_1": [512, [3, 3], 1],
             "conv6": [1024, [3, 3], 2],
             "conv6_1": [1024, [3, 3], 1],
             }

    # from train.prototxt
    loss_weights = np.array([0.32, 0.08, 0.02, 0.01, 0.005])
    #convolutions + relu
    with slim.arg_scope([slim.conv2d],
            weights_regularizer=FLAGS.weights_reg,
			activation_fn=None):
			#TODO: test [1e-3, 1e-4, 1e-5]
    	for key, value in sorted(convs.iteritems()):
            net = slim.conv2d(net, value[0], value[1], value[2], scope=key)
            net = lrelu(net, name=key)
            print(net)
    # Number of upconvolutions
    for i in range(4):
        # flow predict
        # no relu

        with slim.arg_scope([slim.conv2d, slim.conv2d_transpose],
            			    activation_fn=None,
            			     #TODO: test [1e-3, 1e-4, 1e-5],
                            weights_regularizer=FLAGS.weights_reg
            			   ):
            flow_predict = slim.conv2d(
                net, 2, [3, 3], 1, scope='predict_flow_' + str(6 - i))
            flow_up = slim.conv2d_transpose(
                flow_predict, 2, [4, 4], 2, scope='flow_up_' + str(6 - i) + "_to_" + str(5 - i))

    	_, height, width, _ = flow_predict.get_shape().as_list()
        downsample = tf.image.resize_nearest_neighbor(flows, [height, width])
            # add L1 loss
    	tf.losses.absolute_difference(flow_predict, downsample,
                                    loss_weights[i], scope='absolute_loss_' + str(6 - i))

        # deconv + relu
        with slim.arg_scope([slim.conv2d_transpose],
                            activation_fn=None,
                            #TODO: test [1e-3, 1e-4, 1e-5]
                            weights_regularizer=FLAGS.weights_reg
                            ):
	        deconv = slim.conv2d_transpose(net, 512 / 2**i, [4, 4], 2, scope='deconv_' + str(5 - i))
        deconv = lrelu(deconv)
        # get old convolution
        to_concat = tf.get_default_graph().get_tensor_by_name('conv' + str(5 - i) + "_1_Relu/add:0")
        # concat convX_1, deconv, flow_up
        net = tf.concat([to_concat, deconv, flow_up], FLAGS.img_shape[-1], name='concat_' + str(5 - i))

    # last prediction
    with slim.arg_scope([slim.conv2d],
                        activation_fn=None,
                        #TODO: test [1e-3, 1e-4, 1e-5]
            			 weights_regularizer=FLAGS.weights_reg
            			):
        flow_predict = slim.conv2d(net, 2, [3, 3], 1, scope='flow_pred')
    # resize  with ResizeMethod.BILINEAR ?
    # check if this sampling is correct by visualisation
    flow_up = tf.image.resize_bilinear(flow_predict, FLAGS.img_shape[:2])
    tf.losses.absolute_difference(flow_up, flows, loss_weights[4], scope='absolute_loss_' + str(6 - 4))

    return flow_up
