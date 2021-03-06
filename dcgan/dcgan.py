"""
"""
import numpy as np
import ore
import os
import tensorflow as tf

from six.moves import range

# experimented workable learning rate:
# LSUN bedroom: 0.00002
# MNIST: 0.0002
tf.app.flags.DEFINE_float(
    'learning-rate',
    0.00002,
    'learning rate for adam optimizer. 0.00002 is good for LSUN while 0.0002'
    ' is good for MNIST')
tf.app.flags.DEFINE_string(
    'logs-dir-path',
    './dcgan/logs/',
    'path to the directory for storing logs')
tf.app.flags.DEFINE_string(
    'checkpoints-dir-path',
    './dcgan/ckpts/',
    'path to the directory for storing checkpoints')
tf.app.flags.DEFINE_boolean(
    'use-lsun',
    False,
    'use LSUN bedroom dataset instead of MNIST')
tf.app.flags.DEFINE_integer(
    'batch-size',
    64,
    'batch size for training')
tf.app.flags.DEFINE_integer(
    'seed-size',
    128,
    'size of the z for the generator')
tf.app.flags.DEFINE_integer(
    'summary-col-size',
    8,
    'number of columns to summary generated images')

FLAGS = tf.app.flags.FLAGS


def sanity_check():
    """
    """
    if not tf.gfile.Exists(FLAGS.logs_dir_path):
        raise Exception(
            'bad logs dir path: {}'.format(FLAGS.logs_dir_path))

    if not tf.gfile.Exists(FLAGS.checkpoints_dir_path):
        raise Exception(
            'bad checkpoints dir path: {}'.format(FLAGS.checkpoints_dir_path))

    if FLAGS.learning_rate == 0.0:
        raise Exception('learning rate should not be zero :)')

    if FLAGS.batch_size < 1:
        raise Exception('bad batch size: {}'.format(FLAGS.batch_size))

    if FLAGS.seed_size < 1:
        raise Exception('bad seed size: {}'.format(FLAGS.seed_size))

    if FLAGS.summary_col_size < 1:
        raise Exception(
            'bad summary col size: {}'.format(FLAGS.summary_col_size))

    if FLAGS.batch_size % FLAGS.summary_col_size != 0:
        message = '{} % {} != 0'.format(
            FLAGS.batch_size, FLAGS.summary_col_size)

        raise Exception('bad summary size: {}'.format(message))


def leaky_relu(x, leak=0.2, name="lrelu"):
    """
    """
    return tf.maximum(x * leak, x)


def build_discriminator(flow, reuse):
    """
    Build an autoencoder network.

    flow:
        A [N, 32, 32, C] tensor.
    reuse:
        Both discriminator and generator loss share the same discriminator
        network.
    """
    # initial the weight in D from N(0, 0.02)
    weights_initializer = tf.truncated_normal_initializer(stddev=0.02)

    num_layers = 4 if FLAGS.use_lsun else 3

    for layer_idx in range(num_layers):
        if FLAGS.use_lsun:
            num_outputs = 2 ** (7 + layer_idx)
        else:
            num_outputs = 2 ** (4 + layer_idx)

        # arXiv:1511.06434v2
        # in discriminator, use batch norm except input layer
        if layer_idx == 0:
            normalizer_fn = None
        else:
            normalizer_fn = tf.contrib.layers.batch_norm

        # kernal_size must be at least 3. it produce grid effect if the
        # kernal_size is 2 (pixel values do not be broadcasted).
        flow = tf.contrib.layers.convolution2d(
            inputs=flow,
            num_outputs=num_outputs,
            kernel_size=5,
            stride=2,
            padding='SAME',
            activation_fn=leaky_relu,
            normalizer_fn=normalizer_fn,
            weights_initializer=weights_initializer,
            scope='d_{}'.format(layer_idx),
            reuse=reuse)

    # for fully connected layer
    flow = tf.contrib.layers.flatten(flow)

    # fully connected layer to binary classify
    flow = tf.contrib.layers.fully_connected(
        inputs=flow,
        num_outputs=1,
        activation_fn=tf.nn.sigmoid,
        weights_initializer=weights_initializer,
        scope='d_out',
        reuse=reuse)

    return flow


def build_generator(flow):
    """
    build the generator network.

    flow:
        a [None, seed_size] tensor. random seeds for generating images.
    """
    # initial the weight in G from N(0, 0.02)
    weights_initializer = tf.truncated_normal_initializer(stddev=0.02)

    # fully connected layer to upscale the seed for the input of
    # convolutional net.
    num_outputs = 4 * 4 * 1024 if FLAGS.use_lsun else 4 * 4 * 256

    flow = tf.contrib.layers.fully_connected(
        inputs=flow,
        num_outputs=num_outputs,
        activation_fn=tf.nn.relu,
        normalizer_fn=tf.contrib.layers.batch_norm,
        weights_initializer=weights_initializer,
        scope='g_project')

    # reshape to images
    if FLAGS.use_lsun:
        flow = tf.reshape(flow, [-1, 4, 4, 1024])
    else:
        flow = tf.reshape(flow, [-1, 4, 4, 256])

    num_layers = 4 if FLAGS.use_lsun else 3

    # transpose convolution to upscale
    for layer_idx in range(num_layers):
        if layer_idx + 1 == num_layers:
            activation_fn = tf.nn.tanh
            normalizer_fn = None
            num_outputs = 3 if FLAGS.use_lsun else 1
        else:
            activation_fn = tf.nn.relu
            normalizer_fn = tf.contrib.layers.batch_norm

            if FLAGS.use_lsun:
                num_outputs = 2 ** (9 - layer_idx)
            else:
                num_outputs = 2 ** (6 - layer_idx)

        flow = tf.contrib.layers.convolution2d_transpose(
            inputs=flow,
            num_outputs=num_outputs,
            kernel_size=5,
            stride=2,
            padding='SAME',
            activation_fn=activation_fn,
            normalizer_fn=normalizer_fn,
            weights_initializer=weights_initializer,
            scope='g_conv_{}'.format(layer_idx))

    return flow


def build_dcgan():
    """
    """
    # global step
    global_step = tf.get_variable(
        "global_step",
        [],
        trainable=False,
        initializer=tf.constant_initializer(0, dtype=tf.int64),
        dtype=tf.int64)

    # the input batch placeholder for the generator.
    seed = tf.placeholder(shape=[None, FLAGS.seed_size], dtype=tf.float32)

    # the input batch placeholder (real data) for the discriminator.
    if FLAGS.use_lsun:
        real = tf.placeholder(shape=[None, 64, 64, 3], dtype=tf.float32)
    else:
        real = tf.placeholder(shape=[None, 32, 32, 1], dtype=tf.float32)

    # build the generator to generate images from random seeds.
    fake = build_generator(seed)

    # build the discriminator to judge the real data.
    discriminate_real = build_discriminator(real, False)

    # build the discriminator to judge the fake data.
    # judge both real and fake data with the same network (shared).
    discriminate_fake = build_discriminator(fake, True)

    discriminator_temp = discriminate_real * (1.0 - discriminate_fake)
    discriminator_temp = tf.clip_by_value(discriminator_temp, 1e-10, 1.0)
    generator_temp = tf.clip_by_value(discriminate_fake, 1e-10, 1.0)

    discriminator_loss = -tf.reduce_mean(tf.log(discriminator_temp))
    generator_loss = -tf.reduce_mean(tf.log(generator_temp))

    #
    t_vars = tf.trainable_variables()

    d_variables = [v for v in t_vars if v.name.startswith('d_')]
    g_variables = [v for v in t_vars if v.name.startswith('g_')]

    generator_trainer = tf.train.AdamOptimizer(
        learning_rate=FLAGS.learning_rate, beta1=0.5)
    generator_trainer = generator_trainer.minimize(
        generator_loss,
        global_step=global_step,
        var_list=g_variables,
        colocate_gradients_with_ops=False)

    discriminator_trainer = tf.train.AdamOptimizer(
        learning_rate=FLAGS.learning_rate, beta1=0.5)
    discriminator_trainer = discriminator_trainer.minimize(
        discriminator_loss,
        var_list=d_variables,
        colocate_gradients_with_ops=False)

    # variables and gradients
    g_variables_gradients = \
        zip(g_variables, tf.gradients(generator_loss, g_variables))

    d_variables_gradients = \
        zip(d_variables, tf.gradients(discriminator_loss, d_variables))

    return {
        'global_step': global_step,
        'seed': seed,
        'real': real,
        'generator_fake': fake,
        'generator_loss': generator_loss,
        'generator_trainer': generator_trainer,
        'generator_variables_gradients': g_variables_gradients,
        'discriminator_loss': discriminator_loss,
        'discriminator_trainer': discriminator_trainer,
        'discriminator_variables_gradients': d_variables_gradients,
    }


def build_summaries(gan):
    """
    """
    g_summaries = []
    d_summaries = []

    g_summaries.append(
        tf.summary.scalar('generator loss', gan['generator_loss']))

    d_summaries.append(
        tf.summary.scalar('discriminator loss', gan['discriminator_loss']))

    for vg in gan['generator_variables_gradients']:
        variable_name = '{}/variable'.format(vg[0].name)
        gradient_name = '{}/gradient'.format(vg[0].name)

        g_summaries.append(tf.summary.histogram(variable_name, vg[0]))
        g_summaries.append(tf.summary.histogram(gradient_name, vg[1]))

    for vg in gan['discriminator_variables_gradients']:
        variable_name = '{}/variable'.format(vg[0].name)
        gradient_name = '{}/gradient'.format(vg[0].name)

        d_summaries.append(tf.summary.histogram(variable_name, vg[0]))
        d_summaries.append(tf.summary.histogram(gradient_name, vg[1]))

    # fake image
    image_width, image_depth = (64, 3) if FLAGS.use_lsun else (32, 1)

    fake_grid = tf.reshape(
        gan['generator_fake'],
        [1, FLAGS.batch_size * image_width, image_width, image_depth])
    fake_grid = tf.split(fake_grid, FLAGS.summary_col_size, axis=1)
    fake_grid = tf.concat(fake_grid, axis=2)
    fake_grid = tf.saturate_cast(fake_grid * 127.5 + 127.5, tf.uint8)

    summary_generator_fake = tf.summary.image(
        'generated image', fake_grid, max_outputs=1)

    g_summaries_plus = g_summaries + [summary_generator_fake]

    return {
        'summary_generator': tf.summary.merge(g_summaries),
        'summary_generator_plus': tf.summary.merge(g_summaries_plus),
        'summary_discriminator': tf.summary.merge(d_summaries),
    }


def next_real_batch(reader):
    """
    get next batch from mnist.
    """
    raw_batch, _, _ = reader.next_batch(FLAGS.batch_size)

    if FLAGS.use_lsun:
        # crop to 64 x 64 x 3 and copy to numpy array
        discriminator_batch = np.zeros((FLAGS.batch_size, 64, 64, 3))

        for i in range(FLAGS.batch_size):
            image = raw_batch[i]

            w, h = image.shape[:2]

            x, y = (w / 2) - 32, (h / 2) - 32

            discriminator_batch[i] = image[x:x + 64, y:y + 64, :]
    else:
        discriminator_batch = np.reshape(raw_batch, [-1, 28, 28, 1])

        # pad to 32 * 32 images with -1.0
        discriminator_batch = np.pad(
            raw_batch,
            ((0, 0), (2, 2), (2, 2), (0, 0)),
            'constant',
            constant_values=(-1.0, -1.0))

    return discriminator_batch


def next_fake_batch():
    """
    Return random seeds for the generator.
    """
    batch = np.random.uniform(
        -1.0,
        1.0,
        size=[FLAGS.batch_size, FLAGS.seed_size])

    return batch.astype(np.float32)


def train():
    """
    """
    if FLAGS.use_lsun:
        reader = ore.RandomReader(ore.DATASET_LSUN_BEDROOM_TRAINING)
    else:
        reader = ore.RandomReader(ore.DATASET_MNIST_TRAINING)

    # tensorflow
    checkpoint_source_path = tf.train.latest_checkpoint(
        FLAGS.checkpoints_dir_path)
    checkpoint_target_path = os.path.join(
        FLAGS.checkpoints_dir_path, 'model.ckpt')

    gan_graph = build_dcgan()
    summaries = build_summaries(gan_graph)

    reporter = tf.summary.FileWriter(FLAGS.logs_dir_path)

    with tf.Session() as session:
        if checkpoint_source_path is None:
            session.run(tf.global_variables_initializer())
        else:
            tf.train.Saver().restore(session, checkpoint_source_path)

        # give up overlapped old data
        global_step = session.run(gan_graph['global_step'])

        reporter.add_session_log(
            tf.SessionLog(status=tf.SessionLog.START),
            global_step=global_step)

        while True:
            real_sources = next_real_batch(reader)
            fake_sources = next_fake_batch()

            fetches = {
                'discriminator_loss': gan_graph['discriminator_loss'],
                'discriminator_trainer': gan_graph['discriminator_trainer'],
                'summary': summaries['summary_discriminator']
            }

            feeds = {
                gan_graph['seed']: fake_sources,
                gan_graph['real']: real_sources,
            }

            fetched = session.run(fetches, feed_dict=feeds)

            reporter.add_summary(fetched['summary'], global_step)

            #
            fetches = {
                'global_step': gan_graph['global_step'],
                'generator_loss': gan_graph['generator_loss'],
                'generator_trainer': gan_graph['generator_trainer'],
            }

            feeds = {gan_graph['seed']: fake_sources}

            if global_step % 500 == 0:
                fetches['summary'] = summaries['summary_generator_plus']
            else:
                fetches['summary'] = summaries['summary_generator']

            fetched = session.run(fetches, feed_dict=feeds)

            global_step = fetched['global_step']

            reporter.add_summary(fetched['summary'], global_step)

            if global_step % 100 == 0:
                print('[{}]'.format(global_step))

            if global_step % 500 == 0:
                tf.train.Saver().save(
                    session,
                    checkpoint_target_path,
                    global_step=gan_graph['global_step'])


def main(_):
    """
    """
    sanity_check()
    train()


if __name__ == '__main__':
    """
    """
    tf.app.run()
