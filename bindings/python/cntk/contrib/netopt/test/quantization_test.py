import numpy as np
import pytest
import cntk as C
import cntk.contrib.netopt.quantization as qc
C.cntk_py.set_fixed_random_seed(1)

inC, inH, inW = 1, 28, 28
num_classes = 10
feature_var = C.input_variable((inC, inH, inW))
label_var = C.input((num_classes))
dat = np.ones([1, inC, inH, inW], dtype = np.float32)

# create a network with convolutions for the tests
def _create_convolution_model():
    
    with C.layers.default_options(init=C.glorot_uniform(), activation=C.relu):
        h = feature_var
        h = C.layers.Convolution2D(filter_shape=(5,5),
                                           num_filters=8,
                                           strides=(2,2),
                                           pad=True, name='first_convo')(h)
        
        h = C.layers.Convolution2D(filter_shape=(5,5),
                                           num_filters=16,
                                           strides=(2,2),
                                           pad=True, name='second_convo')(h)

        h = C.layers.Convolution2D(filter_shape=(5,5),
                                           num_filters=16,
                                           strides=(1,1),
                                           pad=True, name='thrid_convo')(h)

        h = C.layers.Convolution2D(filter_shape=(5,5),
                                           num_filters=16,
                                           strides=(1,1),
                                           pad=True, name='fourth_convo')(h)
        
        r = C.layers.Dense(num_classes, activation=None, name='classify')(h)
    return r


   
# Exclude the first convolution layer.
def _filter(convolution_block):
    if convolution_block.name and convolution_block.name != 'first_convo':
        return True
    else:
        return False

def test_binarization():

    z = _create_convolution_model()
    binz = qc.binarize_convolution(z)

    blocks = C.logging.graph.depth_first_search(
                binz, (lambda x : type(x) == C.Function and x.is_block and x.op_name =='BinaryConvolution') , depth = 0)
    
    assert(len(blocks) == 4) # all convolution blocks should be converted.

    binz = qc.binarize_convolution(z, _filter)

    blocks = C.logging.graph.depth_first_search(
                binz, (lambda x : type(x) == C.Function and x.is_block and x.op_name =='BinaryConvolution') , depth = 0)
    
    assert(len(blocks) == 3) # now only three of them should be converted.
    assert(all(b.op_name != 'first_convo' for b in blocks))


def test_native_convolution():

    z = _create_convolution_model()
    binz = qc.binarize_convolution(z, _filter)
    
    # save and load to transfer the model to CPU device as native binary
    # convolution does not run on GPU yet.
    model_path = "binary_model.cmf"
    binz.save(model_path)

    eval_device = C.cpu()
    model = C.Function.load(model_path, device=eval_device)
    
    # convert to native halide implementation.
    native_binz = qc.optimize_binary_convolution(model)

    functions = C.logging.graph.depth_first_search(
                native_binz, (lambda x : type(x) == C.Function and x.op_name =='BinaryConvolveOp') , depth = 0)    
    assert(len(functions) == 3)
    
    img_data = np.reshape(dat, (1, 1, 28, 28))
    res = native_binz.eval(img_data, device=eval_device)
    assert(len(res) > 0) # evaluation should work with the new model.