from __future__ import print_function, division

from keras.datasets import mnist
from keras.layers import Input, Dense, Reshape, Flatten, Dropout, multiply
from keras.layers import BatchNormalization, Activation, Embedding, ZeroPadding2D, LSTM
from keras.layers.advanced_activations import LeakyReLU
from keras.layers.convolutional import UpSampling2D, Conv2D, Conv1D, MaxPooling1D
from keras.models import Sequential, Model
from keras.optimizers import Adam
from optparse import OptionParser
from data_proc.data_proc import get_audio_from_files
from sys import getsizeof
from scipy.io.wavfile import read, write

import tensorflow as tf
import matplotlib.pyplot as plt
import numpy as np
import uuid
import os

def build_audio_generator(latent_dim, num_classes, audio_shape):
    model = Sequential()
    model.add(LSTM(512, input_dim=latent_dim, return_sequences=True))
    model.add(Dropout(0.3))
    model.add(LSTM(512, return_sequences=True))
    model.add(Dropout(0.3))
    model.add(LSTM(512))
    model.add(Dense(256))
    model.add(Dropout(0.3))
    model.add(Dense(audio_shape[0]))
    model.add(Activation('tanh'))
    model.add(Reshape((audio_shape[0], 1)))

    model.summary()

    noise = Input(shape=(None, latent_dim,))

    sound = model(noise)

    return Model([noise], sound)

def build_audio_discriminator(audio_shape, num_classes):
    model = Sequential()

    model.add(Conv1D(32, kernel_size=(2), padding="same", input_shape=audio_shape))
    model.add(MaxPooling1D(pool_size=(2)))
    model.add(Dropout(0.25))
    model.add(Dense(128, activation='relu'))
    model.add(Dropout(0.25))
    model.add(Dense(128))

    model.summary()

    audio = Input(shape=audio_shape)

    # Extract feature representation
    features = model(audio)

    # Determine validity and label of the image
    validity = Dense(1, activation="sigmoid")(features)

    return Model(audio, [validity])

def pre_process_data(batch_size):
    parent_dir = 'cv-valid-train'
    tr_sub_dirs_training = 'data'
    sr_training, y_train, X_train = get_audio_from_files(batch_size, parent_dir, tr_sub_dirs_training)

    y_train = y_train.reshape(-1, 1)
    return sr_training, y_train, X_train

def train(sr_training, y_train, X_train, generator, discriminator, combined, epochs, batch_size):

    half_batch = int(batch_size / 2)

    for epoch in range(epochs):

        # ---------------------
        #  Train Discriminator
        # ---------------------

        # Select a random half batch of images
        idx = np.random.randint(0, X_train.shape[0], half_batch)
        audio = X_train[idx]
        half_batch_size = int(audio.shape[1]/2)

        noise = np.random.normal(0, 1, (1, half_batch, 100))

        # The labels of the digits that the generator tries to create an
        # image representation of
        sampled_labels = 1

        # Generate a half batch of new images
        gen_imgs = generator.predict([noise])

        valid = np.ones((half_batch, half_batch_size, 1))
        fake = np.zeros((half_batch, half_batch_size, 1))

        img_labels = y_train[idx]
        fake_labels = 10 * np.ones(half_batch).reshape(-1, 1)


        # Train the discriminator
        d_loss_real = discriminator.train_on_batch(audio, valid)
        d_loss_fake = discriminator.train_on_batch(gen_imgs, fake)
        d_loss = 0.5 * np.add(d_loss_real, d_loss_fake)

        # ---------------------
        #  Train Generator
        # ---------------------

        # Sample generator input
        noise = np.random.normal(0, 1, (1, batch_size, 100))

        valid = np.ones((1, half_batch_size, 1))

        # Train the generator
        g_loss = combined.train_on_batch(noise, valid)

        # Plot the progress
        print (epoch ," Disc loss: " , str(d_loss) , " | Gen loss: " , str(g_loss))

    model_uuid = save_model(generator, discriminator, combined)
    print('Model id: ' + model_uuid)
    new_audio = get_audio_from_model(generator, sr_training, 5, X_train, audio.shape[1])
    print(new_audio)
    write("test.wav", sr_training, new_audio)


def get_audio_from_model(model, sr, duration, seed_audio, frame_size):
    print ('Generating audio...')
    new_audio = np.zeros((sr * duration))
    curr_sample_idx = 0
    pred_audio = model.predict(np.random.normal(0, 1, (1, 1, 100)))
    pred_audio = pred_audio.reshape(pred_audio.shape[1])
    while curr_sample_idx < new_audio.shape[0]:
        new_audio[curr_sample_idx] = pred_audio[curr_sample_idx]
        curr_sample_idx += 1
    print ('Audio generated.')
    return new_audio.astype(np.float)



def sample_images(generator, epoch):
    r, c = 10, 10
    noise = np.random.normal(0, 1, (r * c, 100))
    sampled_labels = np.array([num for _ in range(r) for num in range(c)])

    gen_imgs = generator.predict([noise, sampled_labels])

    # Rescale images 0 - 1
    gen_imgs = 0.5 * gen_imgs + 0.5

    fig, axs = plt.subplots(r, c)
    cnt = 0
    for i in range(r):
        for j in range(c):
            axs[i,j].imshow(gen_imgs[cnt,:,:,0], cmap='gray')
            axs[i,j].axis('off')
            cnt += 1
    fig.savefig("images/%d.png" % epoch)
    print('Creating imgs')
    plt.close()

def save_model(generator, discriminator, combined):

    model_uuid = str(uuid.uuid1())
    def save(model, model_name):
        model_path = "saved_model/"+model_name+"/model.json"
        weights_path = "saved_model/"+model_name+"/model_weights.hdf5"
        if not os.path.exists(model_path) or not os.path.exists(weights_path):
            os.makedirs(os.path.dirname(model_path))

        options = {"file_arch": model_path,
                    "file_weight": weights_path}
        json_string = model.to_json()
        open(options['file_arch'], 'w').write(json_string)
        model.save_weights(options['file_weight'])

    save(generator, model_uuid)
    save(discriminator, model_uuid)
    save(combined, model_uuid)

    return model_uuid
