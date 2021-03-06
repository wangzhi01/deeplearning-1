#coding:utf-8
import numpy as np
import pdb
import math
from . import data_generators
import copy


def calc_iou(R, img_data, C, class_mapping):
	'''
	生成classifier网络的训练的数据
	:param R:预选框
	:param img_data:图片信息
	:param C:训练信息
	:param class_mapping:类别与映射数字之间的关系
	:return:返回 1：筛选后的预选框，2：对应的类别，3：相应的回归梯度，4：交并比
	'''
	bboxes = img_data['bboxes']
	(width, height) = (img_data['width'], img_data['height'])
	# get image dimensions for resizing
	(resized_width, resized_height) = data_generators.get_new_img_size(width, height, C.im_size)

	gta = np.zeros((len(bboxes), 4))

	for bbox_num, bbox in enumerate(bboxes):
		# get the GT box coordinates, and resize to account for image resizing
		gta[bbox_num, 0] = int(round(bbox['x1'] * (resized_width / float(width))/C.rpn_stride))
		gta[bbox_num, 1] = int(round(bbox['x2'] * (resized_width / float(width))/C.rpn_stride))
		gta[bbox_num, 2] = int(round(bbox['y1'] * (resized_height / float(height))/C.rpn_stride))
		gta[bbox_num, 3] = int(round(bbox['y2'] * (resized_height / float(height))/C.rpn_stride))

    # 记录感兴趣区域
	x_roi = []
	y_class_num = []
	y_class_regr_coords = []
	y_class_regr_label = []
    # 记录iou系数
	IoUs = [] # for debugging only

	for ix in range(R.shape[0]):
		(x1, y1, x2, y2) = R[ix, :]
		x1 = int(round(x1))
		y1 = int(round(y1))
		x2 = int(round(x2))
		y2 = int(round(y2))

		best_iou = 0.0
		best_bbox = -1
        # len(bboxes)增强图片中有多少个bboxes
		for bbox_num in range(len(bboxes)):
			curr_iou = data_generators.iou([gta[bbox_num, 0], gta[bbox_num, 2], gta[bbox_num, 1], gta[bbox_num, 3]], [x1, y1, x2, y2])
			if curr_iou > best_iou:
				best_iou = curr_iou
				best_bbox = bbox_num

		if best_iou < C.classifier_min_overlap:# 0.1
				continue
		else:
			w = x2 - x1
			h = y2 - y1
			x_roi.append([x1, y1, w, h])
			IoUs.append(best_iou)

            # 0.1<= best_iou<= 0.5
			if C.classifier_min_overlap <= best_iou < C.classifier_max_overlap:
				# hard negative example
				cls_name = 'bg'
			elif C.classifier_max_overlap <= best_iou:
				cls_name = bboxes[best_bbox]['class']
				cxg = (gta[best_bbox, 0] + gta[best_bbox, 1]) / 2.0
				cyg = (gta[best_bbox, 2] + gta[best_bbox, 3]) / 2.0

				cx = x1 + w / 2.0
				cy = y1 + h / 2.0

				tx = (cxg - cx) / float(w)
				ty = (cyg - cy) / float(h)
				tw = np.log((gta[best_bbox, 1] - gta[best_bbox, 0]) / float(w))
				th = np.log((gta[best_bbox, 3] - gta[best_bbox, 2]) / float(h))
			else:
				print('roi = {}'.format(best_iou))
				raise RuntimeError

        # 转为one-hot形式
		class_num = class_mapping[cls_name]
		class_label = len(class_mapping) * [0]
		class_label[class_num] = 1

		y_class_num.append(copy.deepcopy(class_label))
        # 存储边框的回归梯度
		coords = [0] * 4 * (len(class_mapping) - 1)
        # 决定是否要加入计算Loss
		labels = [0] * 4 * (len(class_mapping) - 1)
		if cls_name != 'bg':
			label_pos = 4 * class_num
            # [8.0 , 8.0 , 4.0 , 4.0]
			sx, sy, sw, sh = C.classifier_regr_std
			coords[label_pos:4+label_pos] = [sx*tx, sy*ty, sw*tw, sh*th]
			labels[label_pos:4+label_pos] = [1, 1, 1, 1]
			y_class_regr_coords.append(copy.deepcopy(coords))
			y_class_regr_label.append(copy.deepcopy(labels))
		else:
			y_class_regr_coords.append(copy.deepcopy(coords))
			y_class_regr_label.append(copy.deepcopy(labels))

	if len(x_roi) == 0:
		return None, None, None, None

	X = np.array(x_roi)
    # 列别的one-hot编码
	Y1 = np.array(y_class_num)
	Y2 = np.concatenate([np.array(y_class_regr_label),np.array(y_class_regr_coords)],axis=1)

	return np.expand_dims(X, axis=0), np.expand_dims(Y1, axis=0), np.expand_dims(Y2, axis=0), IoUs

def apply_regr(x, y, w, h, tx, ty, tw, th):
	try:
		cx = x + w/2.
		cy = y + h/2.
		cx1 = tx * w + cx
		cy1 = ty * h + cy
		w1 = math.exp(tw) * w
		h1 = math.exp(th) * h
		x1 = cx1 - w1/2.
		y1 = cy1 - h1/2.
		x1 = int(round(x1))
		y1 = int(round(y1))
		w1 = int(round(w1))
		h1 = int(round(h1))

		return x1, y1, w1, h1

	except ValueError:
		return x, y, w, h
	except OverflowError:
		return x, y, w, h
	except Exception as e:
		print(e)
		return x, y, w, h

def apply_regr_np(X, T):
	'''
	坐标回归
	:param X: 类型numpy.ndarray，锚点坐标
	:param T: 类型numpy.ndarray
	:return:返回框的坐标[cx , cy , w , h]
	'''
	
	try:
		x = X[0, :, :]
		y = X[1, :, :]
		w = X[2, :, :]
		h = X[3, :, :]

		tx = T[0, :, :]
		ty = T[1, :, :]
		tw = T[2, :, :]
		th = T[3, :, :]

		cx = x + w/2.
		cy = y + h/2.
		cx1 = tx * w + cx
		cy1 = ty * h + cy
		
		print("--------------------------------------------")
		print("tw:" , tw)
		print("th:" , th)
		print("--------------------------------------------")

        # w1 = pw * exp(tw)
		w1 = np.exp(tw.astype(np.float64)) * w
        # h1 = ph * exp(th)
		h1 = np.exp(th.astype(np.float64)) * h
		x1 = cx1 - w1/2.
		y1 = cy1 - h1/2.

		x1 = np.round(x1)
		y1 = np.round(y1)
		w1 = np.round(w1)
		h1 = np.round(h1)
		return np.stack([x1, y1, w1, h1])
	except Exception as e:
		print(e)
		return X

def non_max_suppression_fast(boxes, probs, overlap_thresh=0.9, max_boxes=300):
	'''
	非极大抑制，过滤掉重合度高的region并保留最优的
	:param boxes:[2 * num_anchors * height * width , 4]
	:param probs:[1 , batch * 2 * num_anchors * height * width]
	:param overlap_thresh:
	:param max_boxes:
	:return:
	'''
	# code used from here: http://www.pyimagesearch.com/2015/02/16/faster-non-maximum-suppression-python/
	# if there are no boxes, return an empty list
	if len(boxes) == 0:
		return []

	# grab the coordinates of the bounding boxes
	x1 = boxes[:, 0]
	y1 = boxes[:, 1]
	x2 = boxes[:, 2]
	y2 = boxes[:, 3]

	np.testing.assert_array_less(x1, x2)
	np.testing.assert_array_less(y1, y2)

	# if the bounding boxes integers, convert them to floats --
	# this is important since we'll be doing a bunch of divisions
	if boxes.dtype.kind == "i":
		boxes = boxes.astype("float")

	# initialize the list of picked indexes	
	pick = []

	# calculate the areas
	area = (x2 - x1) * (y2 - y1)

	# sort the bounding boxes 
	idxs = np.argsort(probs)

	# keep looping while some indexes still remain in the indexes
	# list
	while len(idxs) > 0:
		# grab the last index in the indexes list and add the
		# index value to the list of picked indexes
		last = len(idxs) - 1
		i = idxs[last]
		pick.append(i)

		# find the intersection

		xx1_int = np.maximum(x1[i], x1[idxs[:last]])
		yy1_int = np.maximum(y1[i], y1[idxs[:last]])
		xx2_int = np.minimum(x2[i], x2[idxs[:last]])
		yy2_int = np.minimum(y2[i], y2[idxs[:last]])

		ww_int = np.maximum(0, xx2_int - xx1_int)
		hh_int = np.maximum(0, yy2_int - yy1_int)

		area_int = ww_int * hh_int

		# find the union
		area_union = area[i] + area[idxs[:last]] - area_int

		# compute the ratio of overlap
		overlap = area_int/(area_union + 1e-6)

		# delete all indexes from the index list that have
		idxs = np.delete(idxs, np.concatenate(([last],
			np.where(overlap > overlap_thresh)[0])))

		if len(pick) >= max_boxes:
			break

	# return only the bounding boxes that were picked using the integer data type
	boxes = boxes[pick].astype("int")
	probs = probs[pick]
	return boxes, probs

import time
def rpn_to_roi(rpn_layer, regr_layer, C, dim_ordering, use_regr=True, max_boxes=300,overlap_thresh=0.9):
	'''
    将rpn网络的预测结果转化到一个个预选框
	:param rpn_layer:分类信息 [batch ,height , widht , 2 * num_anchors] 表示框对应的概率
	:param regr_layer:回归信息[batch ,height , widht , 8 * num_anchors]每个框对应的回归梯度
	:param C:
	:param dim_ordering:
	:param use_regr:
	:param max_boxes:取多少个框
	:param overlap_thresh:重叠度阈值
	:return:返回指定数量的预选框，格式为(x1,y1,x2,y2)
	'''

	regr_layer = regr_layer / C.std_scaling

	anchor_sizes = C.anchor_box_scales
	anchor_ratios = C.anchor_box_ratios

	assert rpn_layer.shape[0] == 1

	if dim_ordering == 'th':
		(rows,cols) = rpn_layer.shape[2:]

	elif dim_ordering == 'tf':
		(rows, cols) = rpn_layer.shape[1:3]

	curr_layer = 0
	if dim_ordering == 'tf':
        # A.shape = (4 , height , width , 2 * num_anchors)
		A = np.zeros((4, rpn_layer.shape[1], rpn_layer.shape[2], rpn_layer.shape[3]))
	elif dim_ordering == 'th':
		A = np.zeros((4, rpn_layer.shape[2], rpn_layer.shape[3], rpn_layer.shape[1]))

	for anchor_size in anchor_sizes:
		for anchor_ratio in anchor_ratios:
            # 得到框的长宽在原图上的映射
			anchor_x = (anchor_size * anchor_ratio[0])/C.rpn_stride
			anchor_y = (anchor_size * anchor_ratio[1])/C.rpn_stride
			if dim_ordering == 'th':
				regr = regr_layer[0, 4 * curr_layer:4 * curr_layer + 4, :, :]
			else:
                # 得到框对应的回归梯度，将深度都放到第一个维度
				regr = regr_layer[0, :, :, 4 * curr_layer:4 * curr_layer + 4]
				# regr.shape : [4 , height , width]
				regr = np.transpose(regr, (2, 0, 1))

			# 从坐标向量返回坐标矩阵
			# X是rows行cols列的矩阵
            # Y是rows行cols列的矩阵
            # 假设参数1是[0 , 1 , 2] , 参数2是[0 , 1]
            # 则X为[[0 , 1, 2] ,
            #      [0 , 1 , 2]]
            # 则Y为[[0 , 0 , 0] ,
            #      [1 , 1 , 1]]
			X, Y = np.meshgrid(np.arange(cols),np. arange(rows))

            # A.shape = (4 , height , width , 2 * num_anchors)
            # 得到每一个anchor对应的坐标
			A[0, :, :, curr_layer] = X - anchor_x/2
			A[1, :, :, curr_layer] = Y - anchor_y/2
			A[2, :, :, curr_layer] = anchor_x
			A[3, :, :, curr_layer] = anchor_y

			if use_regr:
                # 使用regr对anchor所确定的框进行修正
				A[:, :, :, curr_layer] = apply_regr_np(A[:, :, :, curr_layer], regr)

            # A[0 , : , : , curr_layer] 表示x坐标
            # A[1 , : , : , curr_layer] 表示y坐标
            # A[2 , : , : , curr_layer] 表示w
            # A[3 , : , : , curr_layer] 表示h

			A[2, :, :, curr_layer] = np.maximum(1, A[2, :, :, curr_layer])
			A[3, :, :, curr_layer] = np.maximum(1, A[3, :, :, curr_layer])
            # 转变成 [x1,y1,x2,y2]
			A[2, :, :, curr_layer] += A[0, :, :, curr_layer]
			A[3, :, :, curr_layer] += A[1, :, :, curr_layer]

			A[0, :, :, curr_layer] = np.maximum(0, A[0, :, :, curr_layer])
			A[1, :, :, curr_layer] = np.maximum(0, A[1, :, :, curr_layer])
			A[2, :, :, curr_layer] = np.minimum(cols-1, A[2, :, :, curr_layer])
			A[3, :, :, curr_layer] = np.minimum(rows-1, A[3, :, :, curr_layer])

			curr_layer += 1
    # all_boxes.shape = (2 * num_anchors * height * width  , 4)
	all_boxes = np.reshape(A.transpose((0, 3, 1,2)), (4, -1)).transpose((1, 0))
	# all_probs.shape=(1 , batch * height * width * 2 * num_anchors)
	all_probs = rpn_layer.transpose((0, 3, 1, 2)).reshape((-1))

	x1 = all_boxes[:, 0]
	y1 = all_boxes[:, 1]
	x2 = all_boxes[:, 2]
	y2 = all_boxes[:, 3]

	idxs = np.where((x1 - x2 >= 0) | (y1 - y2 >= 0))

	# 删除指定行
	all_boxes = np.delete(all_boxes, idxs, 0)
	all_probs = np.delete(all_probs, idxs, 0)

	result = non_max_suppression_fast(all_boxes, all_probs, overlap_thresh=overlap_thresh, max_boxes=max_boxes)[0]

	return result
