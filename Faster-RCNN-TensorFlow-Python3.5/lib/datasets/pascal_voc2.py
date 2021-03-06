# --------------------------------------------------------
# Fast R-CNN
# Copyright (c) 2015 Microsoft
# Licensed under The MIT License [see LICENSE for details]
# Written by Ross Girshick and Xinlei Chen
# --------------------------------------------------------
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import pickle
import subprocess
import uuid
import xml.etree.ElementTree as ET

import numpy as np
import scipy.sparse

from lib.config import config as cfg
from lib.datasets.imdb import imdb
# from .voc_eval import voc_eval

from lib.datasets.voc_eval import voc_eval


class pascal_voc(imdb):
    def __init__(self, image_set, year, devkit_path=None):
        '''

        :param image_set: 'train', 'val', 'trainval', 'test'
        :param year:2007 或者2012
        :param devkit_path:
        :return:
        '''
        imdb.__init__(self, 'voc_' + year + '_' + image_set)
        self._year = year
        self._image_set = image_set
        # 'F:\\python\\deeplearning.git\\trunk\\Faster-RCNN-TensorFlow-Python3.5\\data\\VOCdevkit2007'
        self._devkit_path = self._get_default_path() if devkit_path is None \
            else devkit_path
        self._data_path = os.path.join(self._devkit_path, 'VOC' + self._year) # 数据文件，'F:\\python\\deeplearning.git\\trunk\\Faster-RCNN-TensorFlow-Python3.5\\data\\VOCdevkit2007\\VOC2007'
        self._classes = ('__background__',  # always index 0
                         '表面不良', '砂眼', '涂料损伤', '裂纹')
        self._class_to_ind = dict(list(zip(self.classes, list(range(self.num_classes)))))
        self._image_ext = '.jpg'
        self._image_index = self._load_image_set_index() # 保存所有图片的名称（没有后缀.jpg）
        self._roidb_handler = self.gt_roidb
        # 基于随机数获得一个唯一id
        self._salt = str(uuid.uuid4())
        self._comp_id = 'comp4'

        # PASCAL 待定的配置选项
        self.config = {'cleanup': True,
                       'use_salt': True,
                       'use_diff': False,
                       'matlab_eval': False,
                       'rpn_file': None}
        print('self._devkit_path:', self._devkit_path)
        assert os.path.exists(self._devkit_path), \
            'VOCdevkit path does not exist: {}'.format(self._devkit_path)
        assert os.path.exists(self._data_path), \
            'Path does not exist: {}'.format(self._data_path)

    def image_path_at(self, i):
        """
        根据第i个图像样本返回其对应的path，其调用了image_path_from_index(self, index)作为其具体实现
        """
        return self.image_path_from_index(self._image_index[i])

    def image_path_from_index(self, index):
        '''
        返回图片所在的路径
        :param index:是一张图片的名字，假如说有一张图片叫lsq.jpg，这个值就是lsq,没有后缀名
        :return:
        '''
        image_path = os.path.join(self._data_path, 'JPEGImages',
                                  index + self._image_ext)
        assert os.path.exists(image_path), \
            'Path does not exist: {}'.format(image_path)
        return image_path

    def _load_image_set_index(self):
        """
        Load the indexes listed in this dataset's image set file.
        保存所有图片的名称（没有后缀.jpg）
        """
        # Example path to image set file:
        # self._devkit_path + /VOCdevkit2007/VOC2007/ImageSets/Main/val.txt
        # _image_set:val
        image_set_file = os.path.join(self._data_path, 'ImageSets', 'Main',
                                      self._image_set + '.txt')
        assert os.path.exists(image_set_file), \
            'Path does not exist: {}'.format(image_set_file)
        with open(image_set_file) as f:
            image_index = [x.strip() for x in f.readlines()]
        return image_index

    def _get_default_path(self):
        """
        返回PASCAL VOC默认安装的路径
        F:\python\deeplearning.git\trunk\Faster-RCNN-TensorFlow-Python3.5\data\VOCdevkit2007
        """
        return os.path.join(cfg.FLAGS2["data_dir"], 'VOCdevkit' + self._year)

    def gt_roidb(self):
        """
        Return the database of ground-truth regions of interest.
        读取并返回图片gt的db。这个函数就是将图片的gt加载进来。
        其中，pascal_voc图片的gt信息在XML文件中（这个XML文件是pascal_voc数据集本身提供的）
        并且，图片的gt被提前放在了一个.pkl文件里面。（这个.pkl文件需要我们自己生成，代码就在该函数中）
        This function loads/saves from/to a cache file to speed up future calls.
        """
        cache_file = os.path.join(self.cache_path, self.name + '_gt_roidb.pkl')
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as fid:
                try:
                    roidb = pickle.load(fid)
                except:
                    roidb = pickle.load(fid, encoding='bytes')
            print('{} gt roidb loaded from {}'.format(self.name, cache_file))
            return roidb
        # 如果不存在说明是第一次执行本函数
        # gt_roidb 保存获取图片的gt
        gt_roidb = [self._load_pascal_annotation(index)
                    for index in self.image_index if self._load_pascal_annotation(index).__contains__('boxes')]
        print('gt_roidb:' , len(gt_roidb))
        with open(cache_file, 'wb') as fid:
            pickle.dump(gt_roidb, fid, pickle.HIGHEST_PROTOCOL)
        print('wrote gt roidb to {}'.format(cache_file))

        return gt_roidb

    def rpn_roidb(self):
        if int(self._year) == 2017 or self._image_set != 'test':
            gt_roidb = self.gt_roidb()
            rpn_roidb = self._load_rpn_roidb(gt_roidb)
            roidb = imdb.merge_roidbs(gt_roidb, rpn_roidb)
        else:
            roidb = self._load_rpn_roidb(None)

        return roidb

    def _load_rpn_roidb(self, gt_roidb):
        filename = self.config['rpn_file']
        print('loading {}'.format(filename))
        assert os.path.exists(filename), \
            'rpn data not found at: {}'.format(filename)
        with open(filename, 'rb') as f:
            box_list = pickle.load(f)
        return self.create_roidb_from_box_list(box_list, gt_roidb)

    def _load_pascal_annotation(self, index):
        '''
        加载图像和边界box信息
        :param index: 图像文件名，不带后缀.jpg
        :return:
        '''
        path = os.path.join(self._data_path, 'Annotations', index + '.xml') # 例如VOCdevkit/VOC2007/Annotations/000005.xml

        fengji_info = {}
        et = ET.parse(path)
        element_root = et.getroot()
        filename = element_root.find('filename').text
        fengji_info['filename'] = filename

        if filename == 'GanSuQiaoDongC-105-2-0030-1125.jpg':
            print(filename)

        amount = int(element_root.find('amount').text)
        if amount == 0:
            # print('该xml文件为空！' , filename[:-3])
            return fengji_info

        labels = element_root.find('labels')
        label_count = labels.findall('label')

        fengji_index = None
        for i in range(len(label_count)):
            name = labels[i].find('name').text
            if name == '风机':
                fengji_index = i
                break
        if fengji_index == None:
            # print('wrong filename:' , filename[:-3])
            return fengji_info

        color = label_count[fengji_index].find('color').text
        poly_points = label_count[fengji_index].find('points').findall('point')

        # 保存叶片轮廓信息
        polygon_lst = []
        for point in poly_points:
            x = float(point.find('x').text)
            y = float(point.find('y').text)
            polygon_lst.append((x, y))
        fengji_info['polygon'] = polygon_lst

        boxes = np.zeros((len(label_count) - 1, 4), dtype=np.float32)
        gt_class = np.zeros((len(label_count) - 1), dtype=np.int32)
        overlaps = np.zeros((len(label_count) - 1, 5), dtype=np.float32)
        # 记录每个box的面积
        seg_areas = np.zeros((len(label_count) - 1), dtype=np.float32)
        if fengji_index == 0:
            for i in range(1, len(label_count)):
                name = label_count[i].find('name').text
                points = label_count[i].find('points').findall('point')
                defect_info = {}
                defect_info['class'] = name
                polygon = []

                xmin = 10000.0
                ymin = 10000.0
                xmax = -10000.0
                ymax = -10000.0

                for point in points:
                    x = float(point.find('x').text)
                    y = float(point.find('y').text)
                    polygon.append((x, y))

                    xmax = max(x, xmax)
                    ymax = max(y, ymax)
                    xmin = min(x, xmin)
                    ymin = min(y, ymin)
                boxes[i - 1, :] = [xmin, ymin, xmax, ymax]

                if name == '表面不良':
                    gt_class[i - 1] = 1
                elif name == '砂眼':
                    gt_class[i - 1] = 2
                elif name == '涂料损伤':
                    gt_class[i - 1] = 3
                else:
                    gt_class[i - 1] = 4

                overlaps[i - 1, gt_class[i - 1]] = 1.0
                seg_areas[i - 1] = (xmax - xmin + 1) * (ymax - ymin + 1)
        else:
            for i in range(0, fengji_index):
                name = label_count[i].find('name').text
                points = label_count[i].find('points').findall('point')
                defect_info = {}
                defect_info['class'] = name
                polygon = []

                xmin = 10000
                ymin = 10000
                xmax = -10000
                ymax = -10000

                for point in points:
                    x = float(point.find('x').text)
                    y = float(point.find('y').text)
                    polygon.append((x, y))

                    xmax = max(x, xmax)
                    ymax = max(y, ymax)
                    xmin = min(x, xmin)
                    ymin = min(y, ymin)
                boxes[i, :] = [xmin, ymin, xmax, ymax]

                if name == '表面不良':
                    gt_class[i] = 1
                elif name == '砂眼':
                    gt_class[i] = 2
                elif name == '涂料损伤':
                    gt_class[i] = 3
                else:
                    gt_class[i] = 4

                overlaps[i, gt_class[i]] = 1.0
                seg_areas[i] = (xmax - xmin + 1) * (ymax - ymin + 1)

            for i in range(fengji_index + 1, len(label_count)):
                name = label_count[i].find('name').text
                points = label_count[i].find('points').findall('point')
                defect_info = {}
                defect_info['class'] = name
                polygon = []

                xmin = 10000
                ymin = 10000
                xmax = -10000
                ymax = -10000

                for point in points:
                    x = float(point.find('x').text)
                    y = float(point.find('y').text)
                    polygon.append((x, y))

                    xmax = max(x, xmax)
                    ymax = max(y, ymax)
                    xmin = min(x, xmin)
                    ymin = min(y, ymin)
                boxes[i - 1, :] = [xmin, ymin, xmax, ymax]

                if name == '表面不良':
                    gt_class[i - 1] = 1
                elif name == '砂眼':
                    gt_class[i - 1] = 2
                elif name == '涂料损伤':
                    gt_class[i - 1] = 3
                else:
                    gt_class[i - 1] = 4

                overlaps[i - 1, gt_class[i - 1]] = 1.0
                seg_areas[i - 1] = (xmax - xmin + 1) * (ymax - ymin + 1)

        overlaps = scipy.sparse.csr_matrix(overlaps)
        fengji_info['gt_overlaps'] = overlaps
        fengji_info['flipped'] = False
        fengji_info['seg_areas'] = seg_areas
        fengji_info['boxes'] = boxes
        fengji_info['gt_classes'] = gt_class
        fengji_info['polygon'] = polygon_lst
        fengji_info['color'] = color
        return fengji_info

    def _get_comp_id(self):
        comp_id = (self._comp_id + '_' + self._salt if self.config['use_salt']
                   else self._comp_id)
        return comp_id

    def _get_voc_results_file_template(self):
        # VOCdevkit/results/VOC2007/Main/<comp_id>_det_test_aeroplane.txt
        filename = self._get_comp_id() + '_det_' + self._image_set + '_{:s}.txt'
        path = os.path.join(
            self._devkit_path,
            'results',
            'VOC' + self._year,
            'Main',
            filename)
        return path

    def _write_voc_results_file(self, all_boxes):
        for cls_ind, cls in enumerate(self.classes):
            if cls == '__background__':
                continue
            print('Writing {} VOC results file'.format(cls))
            filename = self._get_voc_results_file_template().format(cls)
            with open(filename, 'wt') as f:
                for im_ind, index in enumerate(self.image_index):
                    dets = all_boxes[cls_ind][im_ind]
                    if dets == []:
                        continue
                    # the VOCdevkit expects 1-based indices
                    for k in range(dets.shape[0]):
                        f.write('{:s} {:.3f} {:.1f} {:.1f} {:.1f} {:.1f}\n'.
                                format(index, dets[k, -1],
                                       dets[k, 0] + 1, dets[k, 1] + 1,
                                       dets[k, 2] + 1, dets[k, 3] + 1))

    def _do_python_eval(self, output_dir='output'):
        annopath = self._devkit_path + '\\VOC' + self._year + '\\Annotations\\' + '{:s}.xml'
        imagesetfile = os.path.join(
            self._devkit_path,
            'VOC' + self._year,
            'ImageSets',
            'Main',
            self._image_set + '.txt')
        cachedir = os.path.join(self._devkit_path, 'annotations_cache')
        aps = []
        # The PASCAL VOC metric changed in 2010
        use_07_metric = True if int(self._year) < 2010 else False
        print('VOC07 metric? ' + ('Yes' if use_07_metric else 'No'))
        if not os.path.isdir(output_dir):
            os.mkdir(output_dir)
        for i, cls in enumerate(self._classes):
            if cls == '__background__':
                continue
            filename = self._get_voc_results_file_template().format(cls)
            rec, prec, ap = voc_eval(
                filename, annopath, imagesetfile, cls, cachedir, ovthresh=0.5,
                use_07_metric=use_07_metric)
            aps += [ap]
            print(('AP for {} = {:.4f}'.format(cls, ap)))
            with open(os.path.join(output_dir, cls + '_pr.pkl'), 'wb') as f:
                pickle.dump({'rec': rec, 'prec': prec, 'ap': ap}, f)
        print(('Mean AP = {:.4f}'.format(np.mean(aps))))
        print('~~~~~~~~')
        print('Results:')
        for ap in aps:
            print(('{:.3f}'.format(ap)))
        print(('{:.3f}'.format(np.mean(aps))))
        print('~~~~~~~~')
        print('')
        print('--------------------------------------------------------------')
        print('Results computed with the **unofficial** Python eval code.')
        print('Results should be very close to the official MATLAB eval code.')
        print('Recompute with `./tools/reval.py --matlab ...` for your paper.')
        print('-- Thanks, The Management')
        print('--------------------------------------------------------------')

    def _do_matlab_eval(self, output_dir='output'):
        print('-----------------------------------------------------')
        print('Computing results with the official MATLAB eval code.')
        print('-----------------------------------------------------')
        path = os.path.join(cfg.FLAGS2["root_dir"], 'lib', 'datasets',
                            'VOCdevkit-matlab-wrapper')
        cmd = 'cd {} && '.format(path)
        cmd += '{:s} -nodisplay -nodesktop '.format('matlab')
        cmd += '-r "dbstop if error; '
        cmd += 'voc_eval(\'{:s}\',\'{:s}\',\'{:s}\',\'{:s}\'); quit;"' \
            .format(self._devkit_path, self._get_comp_id(),
                    self._image_set, output_dir)
        print(('Running:\n{}'.format(cmd)))
        status = subprocess.call(cmd, shell=True)

    def evaluate_detections(self, all_boxes, output_dir):
        self._write_voc_results_file(all_boxes)
        self._do_python_eval(output_dir)
        if self.config['matlab_eval']:
            self._do_matlab_eval(output_dir)
        if self.config['cleanup']:
            for cls in self._classes:
                if cls == '__background__':
                    continue
                filename = self._get_voc_results_file_template().format(cls)
                os.remove(filename)

    def competition_mode(self, on):
        if on:
            self.config['use_salt'] = False
            self.config['cleanup'] = False
        else:
            self.config['use_salt'] = True
            self.config['cleanup'] = True


if __name__ == '__main__':

    d = pascal_voc('trainval', '2007')
    res = d.roidb
    from IPython import embed;

    embed()
