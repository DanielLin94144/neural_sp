#! /usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright 2020 Kyoto University (Hirofumi Inaguma)
#  Apache 2.0  (http://www.apache.org/licenses/LICENSE-2.0)

"""Positional Embeddings."""

import copy
import logging
import math
import numpy as np
import torch
import torch.nn as nn

from neural_sp.models.modules.causal_conv import CausalConv1d


NEG_INF = float(np.finfo(np.float32).min)

logger = logging.getLogger(__name__)


class PositionalEncoding(nn.Module):
    """Positional encoding for Transformer.

    Args:
        d_model (int): dimension of MultiheadAttentionMechanism
        dropout (float): dropout probability
        pe_type (str): type of positional encoding
        param_init (str): parameter initialization method
        max_len (int): maximum lenght for sinusoidal positional encoding
        conv_kernel_size (int): window size for 1dconv positional encoding
        layer_norm_eps (float): epsilon value for layer normalization

    """

    def __init__(self, d_model, dropout, pe_type, param_init, max_len=5000,
                 conv_kernel_size=3, layer_norm_eps=1e-12):

        super().__init__()

        self.d_model = d_model
        self.pe_type = pe_type
        self.scale = math.sqrt(self.d_model)

        if '1dconv' in pe_type:
            causal_conv1d = CausalConv1d(in_channels=d_model,
                                         out_channels=d_model,
                                         kernel_size=conv_kernel_size,
                                         param_init=param_init)
            layers = []
            nlayers = int(pe_type.replace('1dconv', '')[0])
            for _ in range(nlayers):
                layers.append(copy.deepcopy(causal_conv1d))
                layers.append(nn.LayerNorm(d_model, eps=layer_norm_eps))
                layers.append(nn.ReLU())
                layers.append(nn.Dropout(p=dropout))
            self.pe = nn.Sequential(*layers)

        elif pe_type != 'none':
            # Compute the positional encodings once in log space.
            pe = torch.zeros(max_len, d_model, dtype=torch.float32)
            position = torch.arange(0, max_len, dtype=torch.float32).unsqueeze(1)
            div_term = torch.exp(torch.arange(0, d_model, 2).float() * -(math.log(10000.0) / d_model))
            pe[:, 0::2] = torch.sin(position * div_term)
            pe[:, 1::2] = torch.cos(position * div_term)
            pe = pe.unsqueeze(0)  # for batch dimension
            self.register_buffer('pe', pe)

        self.dropout = nn.Dropout(p=dropout)

        logger.info('Positional encoding: %s' % pe_type)

    def forward(self, xs, scale=True):
        """Forward pass.

        Args:
            xs (FloatTensor): `[B, T, d_model]`
        Returns:
            xs (FloatTensor): `[B, T, d_model]`

        """
        if scale:
            xs = xs * self.scale
        # NOTE: xs is an embedding without been scaled

        if self.pe_type == 'none':
            xs = self.dropout(xs)
            return xs
        elif self.pe_type == 'add':
            xs = xs + self.pe[:, :xs.size(1)]
            xs = self.dropout(xs)
        elif self.pe_type == 'concat':
            raise NotImplementedError
            xs = torch.cat([xs, self.pe[:, :xs.size(1)].repeat([xs.size(0), 1, 1])], dim=-1)
            # TODO(hirofumi0810): need dimension reduction
            xs = self.dropout(xs)
        elif '1dconv' in self.pe_type:
            xs = self.pe(xs)
        else:
            raise NotImplementedError(self.pe_type)
        return xs


class XLPositionalEmbedding(nn.Module):
    """Positional embedding for TransformerXL."""

    def __init__(self, d_model, dropout):

        super().__init__()

        self.d_model = d_model
        inv_freq = 1 / (10000 ** (torch.arange(0.0, d_model, 2.0) / d_model))
        self.register_buffer("inv_freq", inv_freq)

        self.dropout = nn.Dropout(p=dropout)

    def forward(self, positions):
        """Forward pass.

        Args:
            positions (LongTensor): `[L]`
        Returns:
            pos_emb (LongTensor): `[L, 1, d_model]`

        """
        # outer product
        sinusoid_inp = torch.einsum("i,j->ij", positions.float(), self.inv_freq)
        pos_emb = torch.cat([sinusoid_inp.sin(), sinusoid_inp.cos()], dim=-1)
        pos_emb = self.dropout(pos_emb)
        return pos_emb.unsqueeze(1)
