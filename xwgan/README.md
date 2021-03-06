# Replicated "Improved Training of Wasserstein GANs"

## Commands
python -m xwgan.xwgan_lsun

* **--logs-dir-path** : path to the directory for tensorboard.
* **--outputs-dir-path** : path to the directory for generated images.
* **--checkpoints-dir-path** : path to the directory to keep and load checkpoints.
* **--batch-size** : batch size of training / generating size.
* **--seed-size** : size of seed for fake images.
* **--summary-row-size** : number of images in the row of summary / generated images.
* **--summary-col-size** : number of images in the column of summary / generated images.

## Things to Note
* For LSUN bedroom dataset, both discriminator and generator networks are simplified (less channels).
* Lambda matters. If get NaN during training, try to decrease lambda.

## Results

Trained on MNIST dataset.

![mnist](../assets/xwgan_mnist.png)

### Trained on LSUN bedroom training dataset (lambda=1.0)

![](../assets/xwgan_lsun_wgt_1_40501.png)

![](../assets/xwgan_lsun_wgt_1_loss.png)

### Trained on LSUN bedroom validation dataset (lambda=10.0)

![LSUN beedroom 100501 steps](../assets/xwgan_lsun_100501.png)

![LSUN beedroom 101001 steps](../assets/xwgan_lsun_101001.png)

![LSUN beedroom 101501 steps](../assets/xwgan_lsun_101501.png)

![LSUN bedroom interpolated](../assets/xwgan_lsun_interpolated.png)
